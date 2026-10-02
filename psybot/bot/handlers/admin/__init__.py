from aiogram import Router

from ...filters import IsAdmin
from . import journal, panel, questions, slots

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())
router.include_routers(panel.router, slots.router, questions.router, journal.router)
