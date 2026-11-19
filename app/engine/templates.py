"""Fixed wording used when the model is unavailable or its reply breaks the one-question rule,
plus the instructions given to the model when it only has to word a message."""

QUESTIONS = {
    "English": {
        "same_as_previous": "Is this about the same unit as before, {unit} at {project}?",
        "caller_type": "Are you the purchaser, a lawyer, from a bank, or someone else?",
        "caller_name": "May I have your name, please?",
        "organisation": "Which firm or bank are you from?",
        "project": "Which project is the property in?",
        "unit_no": "What is the unit number?",
        "location": "Where is the property located?",
        "summary": "How can we help you with this unit?",
    },
    "Malay": {
        "same_as_previous": "Adakah ini mengenai unit yang sama seperti sebelum ini, {unit} di {project}?",
        "caller_type": "Adakah anda pembeli, peguam, wakil bank, atau lain-lain?",
        "caller_name": "Boleh saya dapatkan nama anda?",
        "organisation": "Anda dari firma atau bank yang mana?",
        "project": "Hartanah ini di projek yang mana?",
        "unit_no": "Apakah nombor unit tersebut?",
        "location": "Di manakah lokasi hartanah ini?",
        "summary": "Bagaimana kami boleh bantu anda mengenai unit ini?",
    },
    "Chinese": {
        "same_as_previous": "请问这次还是关于之前的单位 {project} {unit} 吗？",
        "caller_type": "请问您是买方、律师、银行代表，还是其他人士？",
        "caller_name": "请问您贵姓大名？",
        "organisation": "请问您来自哪一家律师楼或银行？",
        "project": "请问该房产属于哪个项目？",
        "unit_no": "请问单位号码是多少？",
        "location": "请问该房产位于哪里？",
        "summary": "请问关于这个单位，我们可以怎样帮您？",
    },
}

HANDOFF = {
    "English": "Thank you. I have passed your enquiry to {name}, who will follow up with you. Their contact details are below.",
    "Malay": "Terima kasih. Pertanyaan anda telah dimajukan kepada {name}, yang akan menghubungi anda. Butiran untuk dihubungi ada di bawah.",
    "Chinese": "谢谢您。您的询问已转交给 {name}，对方会与您跟进。联系方式如下。",
}

CLOSING = {
    "English": "You're welcome. Just message us here if you need anything else.",
    "Malay": "Sama-sama. Hubungi kami di sini jika anda perlukan apa-apa lagi.",
    "Chinese": "不客气。如有其他需要，请随时在这里联系我们。",
}

# What the model is told when it only has to word the question for one slot.
QUESTION_INSTRUCTIONS = {
    "same_as_previous": "Ask whether this enquiry is about the same unit as last time: unit {unit} at {project}. Ask exactly one question.",
    "caller_type": "Ask whether they are the purchaser, a lawyer, from a bank, or someone else. Ask exactly one question.",
    "caller_name": "Ask for their name. Ask exactly one question.",
    "organisation": "Ask which law firm or bank they are from. Ask exactly one question.",
    "project": "Ask which project (development) the property is in. Ask exactly one question.",
    "unit_no": "Ask for the unit number. Ask exactly one question.",
    "location": "Say you could not find that project in our list, and ask where the property is located. Ask exactly one question.",
    "summary": "Ask how we can help them with this unit. Ask exactly one question.",
}

CALLER_TYPE_ROWS = [
    ("caller_type:purchaser", "Purchaser / Pembeli"),
    ("caller_type:lawyer", "Lawyer / Peguam"),
    ("caller_type:bank", "Bank"),
    ("caller_type:other", "Other / Lain-lain"),
]


def _lang(table: dict, language: str) -> dict | str:
    return table.get(language, table["English"])


def question(slot: str, language: str, **fmt: str) -> str:
    return _lang(QUESTIONS, language)[slot].format(**fmt)


def handoff(language: str, name: str) -> str:
    return _lang(HANDOFF, language).format(name=name)


def closing(language: str) -> str:
    return _lang(CLOSING, language)
