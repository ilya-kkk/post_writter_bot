from aiogram.fsm.state import State, StatesGroup


class UserState:
    START = "start"
    ASK_USER_TYPE = "ask_user_type"
    WAIT_SOURCE = "wait_source"
    WAIT_EXAMPLES = "wait_examples"
    ANALYZING = "analyzing"
    SHOW_ANALYSIS = "show_analysis"
    GENERATING_IDEAS = "generating_ideas"
    WAIT_IDEA_SELECTION = "wait_idea_selection"
    GENERATING_POST = "generating_post"
    FREE_POST_SHOWN = "free_post_shown"
    PAYWALL_SHOWN = "paywall_shown"
    WAIT_TARIFF_SELECTION = "wait_tariff_selection"
    PAYMENT_PENDING = "payment_pending"
    SUBSCRIBED = "subscribed"
    WAIT_CUSTOM_TOPIC = "wait_custom_topic"


class BotStates(StatesGroup):
    ask_user_type = State()
    wait_source = State()
    wait_examples = State()
    analyzing = State()
    show_analysis = State()
    generating_ideas = State()
    wait_idea_selection = State()
    generating_post = State()
    free_post_shown = State()
    paywall_shown = State()
    wait_tariff_selection = State()
    payment_pending = State()
    subscribed = State()
    wait_custom_topic = State()
