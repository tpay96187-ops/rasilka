from aiogram.fsm.state import State, StatesGroup

class CampaignStates(StatesGroup):
    waiting_name = State()                      # Название рассылки
    waiting_template = State()                  # Выбор шаблона
    waiting_accounts = State()                  # Выбор аккаунтов
    waiting_groups_selection_method = State()   # Метод выбора групп (все или отдельно)
    waiting_groups_manual_input = State()       # Ручной ввод ID групп
    waiting_message_interval = State()          # Интервал между сообщениями
    waiting_cycle_interval = State()            # Интервал между циклами
    waiting_daily_limit = State()               # Дневной лимит
