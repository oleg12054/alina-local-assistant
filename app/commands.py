import os


def handle_local_command(user_text, messages, system_prompt, reset_callback):
    command = user_text.lower()

    if not command.startswith("/"):
        return "chat", messages

    if command in {"/exit", "/quit", "/выход"}:
        return "exit", messages

    if command == "/reset":
        print('История чата сброшена.\n')
        return "handled", reset_callback()

    if command == "/prompt":
        print(system_prompt)
        return "handled", messages

    if command == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        return "handled", messages

    if command == "/help":
        print("Доступные команды:")
        print("/help   - показать список команд")
        print("/prompt - показать системный промпт")
        print("/reset  - сбросить историю чата")
        print("/clear  - очистить консоль")
        print()
        return "handled", messages

    # Любая неизвестная команда тоже не уходит в модель
    print(f"Неизвестная команда: {user_text}")
    print("Напиши /help, чтобы посмотреть список команд.\n")
    return "handled", messages