import queue
import threading
import tkinter as tk
import random

from tkinter import scrolledtext

from app.chat_core import (
    SYSTEM_PROMPT,
    create_initial_messages,
    stream_chat_chunks,
    unload_model,
    OllamaUnavailableError,
    ModelUnavailableError,
)

from app.request_router import analyze_request
from app.web_agent import decide_web_plan
from app.web_search import WebSearchError, build_web_context, search_web

from app.commands import handle_local_command
from app.config import MODEL_NAME
from app.prompt import CHARACTER_PROFILE

class AssistantApp:
    def __init__(self):
        self.response_queue = queue.Queue()
        self.display_buffer = ""
        self.full_assistant_text = ""
        self.model_stream_finished = False
        self.is_generating = False
        self.assistant_message_open = False



        self.runtime_error_state = None
        self.shown_long_errors = set()

        self.system_prompt = SYSTEM_PROMPT
        self.messages = create_initial_messages()

        self.command_queue = queue.Queue()
        self.is_running = True

        self.root = tk.Tk()
        self.root.title(f'Чат - {CHARACTER_PROFILE["name"]}')
        self.root.geometry("700x500")

        self.chat_box = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            state="disabled"
        )
        self.chat_box.pack(fill="both",  expand=True, padx=20, pady=20)

        self.input_entry = tk.Text(self.root, height=4, wrap=tk.WORD)

        self.input_entry.pack(fill="x", padx=20, pady=(0, 20))
        self.input_entry.bind("<Return>", self.on_enter_send)
        self.input_entry.bind("<Shift-Return>", self.on_shift_enter)
        self.send_button = tk.Button(self.root, text="Отправить", command=self.on_send)
        self.send_button.pack(padx=10, pady=(0, 10))

        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        self.write_chat("Система", f'Ассистент "{CHARACTER_PROFILE["name"]}" запущен.')
        print("Командное окно активно. Введи /help для списка команд.")

        # self.command_thread = threading.Thread(target=self.command_loop, daemon=True)
        # self.command_thread.start()
        #
        # self.root.after(500, self.process_command_queue)

        self.root.after(1, self.process_response_queue)
        self.root.after(1, self.process_typing_buffer)

    def show_command_feedback(self, user_text: str):
        command = user_text.lower()

        if command == "/reset":
            self.write_chat("Система", "История чата сброшена.")
        elif command == "/prompt":
            self.write_chat("Система", "Системный промпт выведен в терминал.")
        elif command == "/help":
            self.write_chat("Система", "Список команд выведен в терминал.")
        elif command == "/clear":
            pass
        else:
            self.write_chat("Система", f"Команда обработана: {user_text}")

    def build_final_messages(self, base_messages, user_text: str, request_context, web_context: str = ""):
        messages_snapshot = list(base_messages)

        # Мягкая защита от выдумок, но без жёсткого приказа "иди в интернет".
        if request_context.needs_soft_honesty_hint:
            messages_snapshot.append({
                "role": "system",
                "content": (
                    "Пользователь затрагивает контекст, где легко начать фантазировать. "
                    "Сохраняй живой стиль общения, но не выдумывай факты и детали без опоры. "
                    "Если уверенности мало — говори об этом спокойно и естественно."
                )
            })

        if web_context:
            messages_snapshot.append({
                "role": "system",
                "content": web_context
            })

        messages_snapshot.append({"role": "user", "content": user_text})
        return messages_snapshot

    def build_messages_for_request(self, user_text: str):
        messages_snapshot = list(self.messages)

        if should_use_web(user_text):
            # Пока web реально не подключён — включаем честный режим
            messages_snapshot.append({
                "role": "system",
                "content": (
                    "Пользователь спрашивает о конкретном произведении, персонаже, игре "
                    "или контексте, где могут понадобиться внешние факты. "
                    "Если у тебя нет проверенного контекста, не делай вид, что ты знаешь детали. "
                    "Не выдумывай сцены, характеры, сюжетные арки и личное знакомство с тайтлом. "
                    "Опирайся только на слова пользователя и честно говори, если нужен внешний контекст."
                )
            })

        elif should_force_honest_mode(user_text):
            messages_snapshot.append({
                "role": "system",
                "content": (
                    "Если пользователь упоминает конкретный тайтл или персонажа, "
                    "не притворяйся, что знаешь детали произведения без подтверждённого контекста. "
                    "Можно поддержать разговор, опираясь на слова пользователя, но нельзя выдумывать факты."
                )
            })

        messages_snapshot.append({"role": "user", "content": user_text})
        return messages_snapshot

    def on_enter_send(self, event=None):
        self.on_send()
        return "break"

    def on_shift_enter(self, event=None):
        self.input_entry.insert(tk.INSERT, "\n")
        return "break"

    def write_chat(self, author, text):
        self.chat_box.configure(state="normal")
        self.chat_box.insert(tk.END, f"{author}: {text}\n\n")
        self.chat_box.configure(state="disabled")
        self.chat_box.see(tk.END)

    def on_send(self, event=None):
        user_text = self.input_entry.get("1.0", tk.END).strip()
        if not user_text:
            return

        if self.is_generating:
            return

        if self.runtime_error_state is not None:
            self.show_runtime_error(self.runtime_error_state)
            self.input_entry.delete("1.0", tk.END)
            return

        action, messages = handle_local_command(
            user_text,
            self.messages,
            self.system_prompt,
            create_initial_messages,
        )

        if action == "exit":
            self.shutdown()
            return

        if action == "handled":
            self.messages = messages
            self.input_entry.delete("1.0", tk.END)
            self.show_command_feedback(user_text)
            return

        self.input_entry.delete("1.0", tk.END)
        self.write_chat("Ты", user_text)

        # Снимок истории ДО добавления нового сообщения.
        # Это важно: иначе последняя реплика пользователя попадёт в модель дважды.
        base_messages = list(self.messages)
        request_context = analyze_request(user_text)

        # В основную историю сохраняем сообщение один раз.
        self.messages.append({"role": "user", "content": user_text})

        self.is_generating = True
        self.input_entry.config(state="disabled")
        self.send_button.config(state="disabled")

        self.start_assistant_message()

        worker = threading.Thread(
            target=self.generate_response_worker,
            args=(base_messages, user_text, request_context),
            daemon=True,
        )
        worker.start()

    def command_loop(self):
        while self.is_running:
            try:
                user_text = input("Команда: ").strip()
            except EOFError:
                break

            if not user_text:
                continue

            self.command_queue.put(user_text)

    def process_command_queue(self):
        while not self.command_queue.empty():
            user_text = self.command_queue.get()

            action, messages = handle_local_command(
                user_text,
                self.messages,
                self.system_prompt,
                create_initial_messages
            )

            self.messages = messages

            if action == "handled":
                if user_text.lower() == "/reset":
                    self.write_chat("Система", "История чата сброшена.")
                elif user_text.lower() == "/prompt":
                    self.write_chat("Система", "Системный промпт выведен в терминал.")
                elif user_text.lower() == "/clear":
                    pass
                elif user_text.lower() == "/help":
                    self.write_chat("Система", "Список команд выведен в терминал.")
                else:
                    self.write_chat("Система", f"Команда обработана: {user_text}")

            if action == "exit":
                self.shutdown()
                return

        if self.is_running:
            self.root.after(500, self.process_command_queue)

    def shutdown(self):
        if not self.is_running:
            return

        self.is_running = False
        unload_model()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

    def show_runtime_error(self, error_state):
        if error_state not in self.shown_long_errors:
            if error_state == "ollama_unavailable":
                self.write_chat(
                    "Система",
                    "На вашем компьютере Ollama сейчас недоступна.\n"
                    "Чтобы ассистент работал нормально, нужно:\n"
                    "1) установить и запустить Ollama;\n"
                    f"2) запустить модель {CHARACTER_PROFILE['name']} не нужно — нужна именно модель {MODEL_NAME};\n"
                    f"3) например, открыть терминал и выполнить: ollama run {MODEL_NAME}\n\n"
                    "После этого перезапусти приложение."
                )
            elif error_state == "model_unavailable":
                self.write_chat(
                    "Система",
                    f'Ollama запущена, но модель "{MODEL_NAME}" сейчас недоступна.\n'
                    f'Попробуй запустить её командой: ollama run {MODEL_NAME}\n'
                    "После этого перезапусти приложение."
                )

            self.shown_long_errors.add(error_state)
        else:
            if error_state == "ollama_unavailable":
                self.write_chat("Система", "Ollama сейчас не может быть запущена.")
            elif error_state == "model_unavailable":
                self.write_chat("Система", f'Модель "{MODEL_NAME}" сейчас недоступна.')

    def generate_response_worker(self, base_messages, user_text, request_context):
        try:
            web_context = ""

            # 1. Модель делает внутренний черновой шаг:
            #    нужен ли ей внешний контекст именно сейчас.
            web_plan = decide_web_plan(base_messages, user_text)

            # 2. Если она решила, что поиск нужен — даём ей инструмент.
            if web_plan.need_web and web_plan.search_query:
                self.response_queue.put((
                    "system_info",
                    f"Собираю внешний контекст: {web_plan.search_query}"
                ))

                try:
                    results = search_web(web_plan.search_query)
                    web_context = build_web_context(results)
                except WebSearchError:
                    self.response_queue.put((
                        "system_info",
                        "Внешний поиск сейчас не дал уверенного результата, поэтому отвечаю осторожно."
                    ))

            final_messages = self.build_final_messages(
                base_messages=base_messages,
                user_text=user_text,
                request_context=request_context,
                web_context=web_context,
            )

            for piece in stream_chat_chunks(final_messages):
                self.response_queue.put(("chunk", piece))

            self.response_queue.put(("done", None))

        except OllamaUnavailableError:
            self.response_queue.put(("ollama_unavailable", None))
        except ModelUnavailableError:
            self.response_queue.put(("model_unavailable", None))
        except Exception as error:
            self.response_queue.put(("unexpected_error", str(error)))

    def process_response_queue(self):
        while not self.response_queue.empty():
            status, payload = self.response_queue.get()

            if status == "chunk":
                self.display_buffer += payload
                self.full_assistant_text += payload

            elif status == "done":
                self.model_stream_finished = True

            elif status == "system_info":
                self.write_chat("Система", payload)

            elif status == "ollama_unavailable":
                self.is_generating = False
                self.input_entry.config(state="normal")
                self.send_button.config(state="normal")
                self.runtime_error_state = "ollama_unavailable"
                self.show_runtime_error(self.runtime_error_state)
                self.finish_assistant_message(cancelled=True)

            elif status == "model_unavailable":
                self.is_generating = False
                self.input_entry.config(state="normal")
                self.send_button.config(state="normal")
                self.runtime_error_state = "model_unavailable"
                self.show_runtime_error(self.runtime_error_state)
                self.finish_assistant_message(cancelled=True)

            elif status == "unexpected_error":
                self.is_generating = False
                self.input_entry.config(state="normal")
                self.send_button.config(state="normal")
                self.write_chat("Система", f"Неожиданная ошибка: {payload}")
                self.finish_assistant_message(cancelled=True)

        if self.is_running:
            self.root.after(50, self.process_response_queue)

    def process_typing_buffer(self):
        if self.display_buffer:
            chunk_size = random.randint(1, 2)
            piece = self.display_buffer[:chunk_size]
            self.display_buffer = self.display_buffer[chunk_size:]
            self.append_to_assistant_message(piece)

        elif self.model_stream_finished and self.is_generating:
            self.model_stream_finished = False
            self.is_generating = False
            self.input_entry.config(state="normal")
            self.send_button.config(state="normal")

            self.finish_assistant_message()
            self.messages.append({"role": "assistant", "content": self.full_assistant_text})
            self.full_assistant_text = ""

        if self.is_running:
            delay = random.randint(40, 120)
            self.root.after(delay, self.process_typing_buffer)


    def start_assistant_message(self):
        self.assistant_message_open = True
        self.chat_box.configure(state="normal")
        self.chat_box.insert(tk.END, f'{CHARACTER_PROFILE["name"]}: ')
        self.chat_box.configure(state="disabled")
        self.chat_box.see(tk.END)


    def append_to_assistant_message(self, text):
        self.chat_box.configure(state="normal")
        self.chat_box.insert(tk.END, text)
        self.chat_box.configure(state="disabled")
        self.chat_box.see(tk.END)


    def finish_assistant_message(self, cancelled=False):
        if not self.assistant_message_open:
            return

        self.chat_box.configure(state="normal")

        if cancelled and not self.full_assistant_text:
            self.chat_box.insert(tk.END, "[ответ не получен]")

        self.chat_box.insert(tk.END, "\n\n")
        self.chat_box.configure(state="disabled")
        self.chat_box.see(tk.END)

        self.assistant_message_open = False
        self.display_buffer = ""
        self.full_assistant_text = ""
        self.model_stream_finished = False

if __name__ == "__main__":
    app = AssistantApp()
    app.run()