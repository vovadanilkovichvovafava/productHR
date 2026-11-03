"""HR-бот практики и испытательного срока (ТЗ «Пребординг и онбординг трафика»).

- models.py   — таблицы onboarding_* (создаются create_all в api/db/init.py);
- service.py  — сценарии ТЗ, без Telegram (Messenger подставляется);
- schedule.py — расчёт времени сообщений по поясу кандидата;
- telegram.py — кнопки (Router) и хуки для обработчиков api/bot.py;
- runtime.py  — сервис на процесс и воркер расписания (стартует в main.py);
- api/routes/onboarding.py — ручки для карточки кандидата.
"""
