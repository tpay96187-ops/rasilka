from aiogram.fsm.state import State, StatesGroup

class AddAccountStates(StatesGroup):
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()

class TemplateStates(StatesGroup):
    waiting_name = State()
    waiting_content = State()
    waiting_edit_name = State()
    waiting_edit_content = State()

class CampaignStates(StatesGroup):
    waiting_name = State()
    waiting_template = State()
    waiting_accounts = State()
    waiting_groups_selection_method = State()   # выбор метода выбора групп (все / вручную)
    waiting_manual_groups_ids = State()          # ожидание ввода ID групп вручную
    waiting_message_interval = State()
    waiting_cycle_interval = State()
    waiting_daily_limit = State()
