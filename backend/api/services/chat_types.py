"""
Chat type configurations with default presets, quick actions, and AI prompts.
Also includes Entity type default criteria.
"""

from typing import Dict, List, Any


# ============ ENTITY TYPE DEFAULT CRITERIA ============

ENTITY_TYPE_DEFAULT_CRITERIA: Dict[str, List[Dict[str, Any]]] = {
    "candidate": [
        {"name": "Communication Skills", "description": "Clarity, professionalism, responsiveness", "weight": 8, "category": "basic"},
        {"name": "Technical Knowledge", "description": "Demonstrated expertise in required areas", "weight": 9, "category": "basic"},
        {"name": "Problem Solving", "description": "Approach to challenges and solutions", "weight": 7, "category": "basic"},
        {"name": "Team Collaboration", "description": "How they interact with others", "weight": 6, "category": "basic"},
        {"name": "Inconsistent Statements", "description": "Contradictions in claims or experience", "weight": 8, "category": "red_flags"},
        {"name": "Negative Attitude", "description": "Complaints, blame, negativity", "weight": 7, "category": "red_flags"},
        {"name": "Initiative", "description": "Proactive suggestions and engagement", "weight": 6, "category": "green_flags"},
        {"name": "Quick Learner", "description": "Adaptability and learning speed", "weight": 7, "category": "green_flags"},
    ],
    "client": [
        {"name": "Satisfaction Level", "description": "Overall client happiness", "weight": 9, "category": "basic"},
        {"name": "Engagement", "description": "Active participation in communication", "weight": 7, "category": "basic"},
        {"name": "Payment Reliability", "description": "Timely payments and financial stability", "weight": 8, "category": "basic"},
        {"name": "Requirements Clarity", "description": "Clear communication of needs", "weight": 7, "category": "basic"},
        {"name": "Complaints", "description": "Expressed dissatisfaction", "weight": 9, "category": "red_flags"},
        {"name": "Unrealistic Expectations", "description": "Demands beyond agreed scope", "weight": 7, "category": "red_flags"},
        {"name": "Referral Potential", "description": "Likelihood to recommend us", "weight": 6, "category": "green_flags"},
        {"name": "Long-term Partnership", "description": "Interest in ongoing collaboration", "weight": 8, "category": "green_flags"},
    ],
    "contractor": [
        {"name": "Work Quality", "description": "Quality of deliverables", "weight": 9, "category": "basic"},
        {"name": "Deadline Compliance", "description": "Meeting agreed timelines", "weight": 8, "category": "basic"},
        {"name": "Communication", "description": "Responsiveness and clarity", "weight": 7, "category": "basic"},
        {"name": "Cost Efficiency", "description": "Value for money", "weight": 6, "category": "basic"},
        {"name": "Missed Deadlines", "description": "Late deliveries", "weight": 8, "category": "red_flags"},
        {"name": "Quality Issues", "description": "Bugs, errors, revisions needed", "weight": 9, "category": "red_flags"},
        {"name": "Proactive Solutions", "description": "Suggesting improvements", "weight": 6, "category": "green_flags"},
        {"name": "Flexibility", "description": "Adapting to changes", "weight": 7, "category": "green_flags"},
    ],
    "lead": [
        {"name": "Buying Intent", "description": "Seriousness of purchase interest", "weight": 9, "category": "basic"},
        {"name": "Budget Alignment", "description": "Match with our pricing", "weight": 8, "category": "basic"},
        {"name": "Decision Timeline", "description": "Urgency of decision", "weight": 7, "category": "basic"},
        {"name": "Stakeholder Access", "description": "Connection to decision makers", "weight": 7, "category": "basic"},
        {"name": "Price Objections", "description": "Focus on discounts", "weight": 7, "category": "red_flags"},
        {"name": "Competitor Mentions", "description": "Considering alternatives", "weight": 6, "category": "red_flags"},
        {"name": "Urgency Signals", "description": "Need to act fast", "weight": 8, "category": "green_flags"},
        {"name": "Champion Identified", "description": "Internal advocate found", "weight": 8, "category": "green_flags"},
    ],
    "partner": [
        {"name": "Strategic Alignment", "description": "Shared goals and values", "weight": 9, "category": "basic"},
        {"name": "Communication Quality", "description": "Regular and clear updates", "weight": 8, "category": "basic"},
        {"name": "Mutual Benefit", "description": "Value for both parties", "weight": 8, "category": "basic"},
        {"name": "Commitment Level", "description": "Dedication to partnership", "weight": 7, "category": "basic"},
        {"name": "Broken Promises", "description": "Unfulfilled commitments", "weight": 9, "category": "red_flags"},
        {"name": "One-sided Benefits", "description": "Partnership favoring one side", "weight": 7, "category": "red_flags"},
        {"name": "Growth Potential", "description": "Opportunity for expansion", "weight": 7, "category": "green_flags"},
        {"name": "Trust Building", "description": "Increasing reliability over time", "weight": 8, "category": "green_flags"},
    ],
    "custom": [],
}


def get_entity_default_criteria(entity_type: str) -> List[Dict[str, Any]]:
    """Get default criteria for an entity type."""
    return ENTITY_TYPE_DEFAULT_CRITERIA.get(entity_type, [])

# Chat type metadata
CHAT_TYPE_CONFIG: Dict[str, Dict[str, Any]] = {
    "hr": {
        "name": "HR - Candidate Evaluation",
        "description": "Evaluate job candidates based on their communication",
        "icon": "UserCheck",
        "color": "blue",
        "quick_actions": [
            {"id": "full_analysis", "label": "Full Analysis", "icon": "FileText"},
            {"id": "red_flags", "label": "Red Flags", "icon": "AlertTriangle"},
            {"id": "strengths", "label": "Strengths", "icon": "ThumbsUp"},
            {"id": "recommendation", "label": "Recommendation", "icon": "Sparkles"},
            {"id": "culture_fit", "label": "Culture Fit", "icon": "Users"},
        ],
        "suggested_questions": [
            "Is this candidate suitable for the position?",
            "What are the main risks with this candidate?",
            "Compare their experience with what they claim",
            "Rate their communication skills",
            "Would you recommend hiring them?",
        ],
        "default_criteria": [
            {"name": "Communication Skills", "description": "Clarity, professionalism, responsiveness", "weight": 8, "category": "basic"},
            {"name": "Technical Knowledge", "description": "Demonstrated expertise in required areas", "weight": 9, "category": "basic"},
            {"name": "Problem Solving", "description": "Approach to challenges and solutions", "weight": 7, "category": "basic"},
            {"name": "Team Collaboration", "description": "How they interact with others", "weight": 6, "category": "basic"},
            {"name": "Inconsistent Statements", "description": "Contradictions in claims or experience", "weight": 8, "category": "red_flags"},
            {"name": "Negative Attitude", "description": "Complaints, blame, negativity", "weight": 7, "category": "red_flags"},
            {"name": "Initiative", "description": "Proactive suggestions and engagement", "weight": 6, "category": "green_flags"},
            {"name": "Quick Learner", "description": "Adaptability and learning speed", "weight": 7, "category": "green_flags"},
        ],
    },
    "project": {
        "name": "Project - Team Chat",
        "description": "Track project progress, tasks, and team collaboration",
        "icon": "FolderKanban",
        "color": "purple",
        "quick_actions": [
            {"id": "project_status", "label": "Project Status", "icon": "BarChart"},
            {"id": "blockers", "label": "Blockers", "icon": "AlertCircle"},
            {"id": "responsibilities", "label": "Who Does What", "icon": "Users"},
            {"id": "deadlines", "label": "Deadline Risks", "icon": "Clock"},
            {"id": "action_items", "label": "Action Items", "icon": "CheckSquare"},
        ],
        "suggested_questions": [
            "What is the current project status?",
            "Who is responsible for what?",
            "What are the current blockers?",
            "Are there any deadline risks?",
            "What decisions were made recently?",
        ],
        "default_criteria": [
            {"name": "Task Progress", "description": "Completion of assigned tasks", "weight": 9, "category": "basic"},
            {"name": "Communication Quality", "description": "Clear updates and responses", "weight": 7, "category": "basic"},
            {"name": "Deadline Adherence", "description": "Meeting agreed timelines", "weight": 8, "category": "basic"},
            {"name": "Blocker Resolution", "description": "Speed of resolving issues", "weight": 7, "category": "basic"},
            {"name": "Missed Deadlines", "description": "Delays without communication", "weight": 8, "category": "red_flags"},
            {"name": "Scope Creep", "description": "Uncontrolled expansion of work", "weight": 6, "category": "red_flags"},
            {"name": "Proactive Updates", "description": "Regular status updates", "weight": 6, "category": "green_flags"},
            {"name": "Problem Prevention", "description": "Identifying issues early", "weight": 7, "category": "green_flags"},
        ],
    },
    "client": {
        "name": "Client - Customer Communication",
        "description": "Monitor client satisfaction and relationship health",
        "icon": "Building2",
        "color": "green",
        "quick_actions": [
            {"id": "satisfaction", "label": "Satisfaction", "icon": "Smile"},
            {"id": "churn_risk", "label": "Churn Risk", "icon": "AlertTriangle"},
            {"id": "requests", "label": "Requests", "icon": "MessageSquare"},
            {"id": "promises", "label": "Our Promises", "icon": "Handshake"},
            {"id": "sentiment", "label": "Sentiment Analysis", "icon": "Heart"},
        ],
        "suggested_questions": [
            "Is the client satisfied?",
            "What have we promised them?",
            "Is there any negative sentiment?",
            "What are their main requests?",
            "Is there a risk of churn?",
        ],
        "default_criteria": [
            {"name": "Satisfaction Level", "description": "Overall client happiness", "weight": 9, "category": "basic"},
            {"name": "Response Time", "description": "Speed of our responses", "weight": 7, "category": "basic"},
            {"name": "Request Fulfillment", "description": "Delivery on client requests", "weight": 8, "category": "basic"},
            {"name": "Relationship Quality", "description": "Tone and rapport", "weight": 7, "category": "basic"},
            {"name": "Complaints", "description": "Expressed dissatisfaction", "weight": 9, "category": "red_flags"},
            {"name": "Unfulfilled Promises", "description": "Things we said but didn't do", "weight": 8, "category": "red_flags"},
            {"name": "Referral Potential", "description": "Likelihood to recommend us", "weight": 6, "category": "green_flags"},
            {"name": "Expansion Interest", "description": "Interest in more services", "weight": 7, "category": "green_flags"},
        ],
    },
    "contractor": {
        "name": "Contractor - External Partner",
        "description": "Evaluate external contractor performance and reliability",
        "icon": "Briefcase",
        "color": "orange",
        "quick_actions": [
            {"id": "performance", "label": "Performance", "icon": "TrendingUp"},
            {"id": "reliability", "label": "Reliability", "icon": "Shield"},
            {"id": "communication", "label": "Communication", "icon": "MessageCircle"},
            {"id": "issues", "label": "Issues", "icon": "AlertCircle"},
            {"id": "recommendation", "label": "Continue Working?", "icon": "HelpCircle"},
        ],
        "suggested_questions": [
            "Is the contractor meeting expectations?",
            "Are they reliable with deadlines?",
            "What problems have occurred?",
            "How is their communication quality?",
            "Should we continue working with them?",
        ],
        "default_criteria": [
            {"name": "Work Quality", "description": "Quality of deliverables", "weight": 9, "category": "basic"},
            {"name": "Deadline Compliance", "description": "Meeting agreed timelines", "weight": 8, "category": "basic"},
            {"name": "Communication", "description": "Responsiveness and clarity", "weight": 7, "category": "basic"},
            {"name": "Cost Efficiency", "description": "Value for money", "weight": 6, "category": "basic"},
            {"name": "Missed Deadlines", "description": "Late deliveries", "weight": 8, "category": "red_flags"},
            {"name": "Quality Issues", "description": "Bugs, errors, revisions needed", "weight": 9, "category": "red_flags"},
            {"name": "Proactive Solutions", "description": "Suggesting improvements", "weight": 6, "category": "green_flags"},
            {"name": "Flexibility", "description": "Adapting to changes", "weight": 7, "category": "green_flags"},
        ],
    },
    "sales": {
        "name": "Sales - Negotiations",
        "description": "Track sales pipeline and deal progress",
        "icon": "DollarSign",
        "color": "yellow",
        "quick_actions": [
            {"id": "deal_stage", "label": "Deal Stage", "icon": "Target"},
            {"id": "objections", "label": "Objections", "icon": "XCircle"},
            {"id": "budget", "label": "Budget Info", "icon": "Wallet"},
            {"id": "decision_maker", "label": "Decision Maker", "icon": "Crown"},
            {"id": "next_steps", "label": "Next Steps", "icon": "ArrowRight"},
        ],
        "suggested_questions": [
            "What stage is this deal at?",
            "What objections have been raised?",
            "What is their budget?",
            "Who is the decision maker?",
            "What do we need to close this deal?",
        ],
        "default_criteria": [
            {"name": "Buying Intent", "description": "Seriousness of purchase interest", "weight": 9, "category": "basic"},
            {"name": "Budget Alignment", "description": "Match with our pricing", "weight": 8, "category": "basic"},
            {"name": "Decision Timeline", "description": "Urgency of decision", "weight": 7, "category": "basic"},
            {"name": "Stakeholder Engagement", "description": "Involvement of key people", "weight": 7, "category": "basic"},
            {"name": "Price Objections", "description": "Focus on discounts", "weight": 7, "category": "red_flags"},
            {"name": "Competitor Mentions", "description": "Considering alternatives", "weight": 6, "category": "red_flags"},
            {"name": "Urgency Signals", "description": "Need to act fast", "weight": 8, "category": "green_flags"},
            {"name": "Champion Identified", "description": "Internal advocate found", "weight": 8, "category": "green_flags"},
        ],
    },
    "support": {
        "name": "Support - Customer Service",
        "description": "Track support issues and resolution quality",
        "icon": "Headphones",
        "color": "cyan",
        "quick_actions": [
            {"id": "issues_summary", "label": "Issues Summary", "icon": "List"},
            {"id": "resolution_rate", "label": "Resolution Rate", "icon": "CheckCircle"},
            {"id": "response_time", "label": "Response Time", "icon": "Clock"},
            {"id": "sentiment", "label": "Customer Mood", "icon": "Smile"},
            {"id": "escalations", "label": "Escalations", "icon": "ArrowUp"},
        ],
        "suggested_questions": [
            "What are the most common issues?",
            "Are all issues resolved?",
            "How fast are we responding?",
            "Is the customer satisfied with support?",
            "Are there any escalations needed?",
        ],
        "default_criteria": [
            {"name": "Issue Resolution", "description": "Problems fully solved", "weight": 9, "category": "basic"},
            {"name": "Response Speed", "description": "Time to first response", "weight": 8, "category": "basic"},
            {"name": "Customer Satisfaction", "description": "Happy with support", "weight": 8, "category": "basic"},
            {"name": "First Contact Resolution", "description": "Solved without escalation", "weight": 7, "category": "basic"},
            {"name": "Repeated Issues", "description": "Same problem recurring", "weight": 8, "category": "red_flags"},
            {"name": "Escalation Required", "description": "Needed higher level help", "weight": 6, "category": "red_flags"},
            {"name": "Positive Feedback", "description": "Expressed gratitude", "weight": 7, "category": "green_flags"},
            {"name": "Self-Service Success", "description": "Used docs/guides effectively", "weight": 5, "category": "green_flags"},
        ],
    },
    "custom": {
        "name": "Custom",
        "description": "Define your own chat type with custom criteria",
        "icon": "Settings",
        "color": "gray",
        "quick_actions": [
            {"id": "full_analysis", "label": "Full Analysis", "icon": "FileText"},
            {"id": "summary", "label": "Summary", "icon": "AlignLeft"},
            {"id": "key_points", "label": "Key Points", "icon": "List"},
            {"id": "action_items", "label": "Action Items", "icon": "CheckSquare"},
        ],
        "suggested_questions": [
            "What is the main topic of discussion?",
            "What are the key takeaways?",
            "What actions are needed?",
            "Are there any concerns?",
        ],
        "default_criteria": [],
    },
}


def get_chat_type_config(chat_type: str) -> Dict[str, Any]:
    """Get configuration for a specific chat type."""
    return CHAT_TYPE_CONFIG.get(chat_type, CHAT_TYPE_CONFIG["custom"])


def get_all_chat_types() -> List[Dict[str, Any]]:
    """Get all chat types with their basic info."""
    return [
        {
            "id": type_id,
            "name": config["name"],
            "description": config["description"],
            "icon": config["icon"],
            "color": config["color"],
        }
        for type_id, config in CHAT_TYPE_CONFIG.items()
    ]


def get_quick_actions(chat_type: str) -> List[Dict[str, str]]:
    """Get quick actions for a chat type."""
    config = get_chat_type_config(chat_type)
    return config.get("quick_actions", [])


def get_suggested_questions(chat_type: str) -> List[str]:
    """Get suggested AI questions for a chat type."""
    config = get_chat_type_config(chat_type)
    return config.get("suggested_questions", [])


def get_default_criteria(chat_type: str) -> List[Dict[str, Any]]:
    """Get default criteria for a chat type."""
    config = get_chat_type_config(chat_type)
    return config.get("default_criteria", [])


# Universal preset templates that work across all chat types
UNIVERSAL_PRESETS: List[Dict[str, Any]] = [
    {
        "name": "Критическое мышление",
        "description": "Оценка способности анализировать и принимать решения",
        "criteria": [
            {"name": "Анализ информации", "description": "Проверяет факты, задаёт уточняющие вопросы, не принимает всё на веру", "weight": 9, "category": "basic"},
            {"name": "Аргументация позиции", "description": "Обосновывает решения, приводит примеры и доказательства", "weight": 8, "category": "basic"},
            {"name": "Признание ошибок", "description": "Способен признать неправоту и скорректировать позицию", "weight": 7, "category": "green_flags"},
            {"name": "Слепое следование", "description": "Принимает информацию без проверки, не задаёт вопросов", "weight": 8, "category": "red_flags"},
            {"name": "Упёртость", "description": "Отстаивает позицию даже при явных контраргументах", "weight": 7, "category": "red_flags"},
            {"name": "Системное мышление", "description": "Видит связи между явлениями, понимает последствия решений", "weight": 8, "category": "potential"},
        ],
    },
    {
        "name": "Использование AI и инструментов",
        "description": "Как человек использует AI и другие инструменты для работы",
        "criteria": [
            {"name": "AI как инструмент", "description": "Использует AI для ускорения работы, проверяет и адаптирует результаты", "weight": 8, "category": "green_flags"},
            {"name": "Критическая оценка AI", "description": "Понимает ограничения AI, проверяет выходные данные", "weight": 9, "category": "green_flags"},
            {"name": "Слепое доверие AI", "description": "Копипастит результаты AI без проверки, отключает критическое мышление", "weight": 9, "category": "red_flags"},
            {"name": "AI-зависимость", "description": "Не может работать без AI, теряется при простых задачах", "weight": 8, "category": "red_flags"},
            {"name": "Отказ от инструментов", "description": "Принципиально не использует современные инструменты из упрямства", "weight": 6, "category": "red_flags"},
            {"name": "Освоение новых инструментов", "description": "Быстро осваивает новые технологии и находит им применение", "weight": 7, "category": "potential"},
        ],
    },
    {
        "name": "Самостоятельность и командность",
        "description": "Баланс между независимостью и умением работать в команде",
        "criteria": [
            {"name": "Автономность", "description": "Способен работать без постоянного контроля, сам находит решения", "weight": 8, "category": "basic"},
            {"name": "Запрос помощи вовремя", "description": "Знает когда спросить, не тратит время на тупиковые пути", "weight": 7, "category": "green_flags"},
            {"name": "Делится знаниями", "description": "Помогает коллегам, объясняет свои решения", "weight": 6, "category": "green_flags"},
            {"name": "Гиперавтономность", "description": "Не спрашивает когда надо, делает по-своему игнорируя команду", "weight": 8, "category": "red_flags"},
            {"name": "Беспомощность", "description": "Постоянно спрашивает очевидное, не пытается разобраться сам", "weight": 8, "category": "red_flags"},
            {"name": "Токсичная конкуренция", "description": "Скрывает информацию от коллег, подставляет других", "weight": 9, "category": "red_flags"},
        ],
    },
    {
        "name": "Честность и прозрачность",
        "description": "Оценка искренности и открытости в коммуникации",
        "criteria": [
            {"name": "Прямота", "description": "Говорит правду, даже если она неприятная, не юлит", "weight": 8, "category": "green_flags"},
            {"name": "Признание незнания", "description": "Честно говорит 'не знаю' вместо выдумывания", "weight": 8, "category": "green_flags"},
            {"name": "Прозрачность процесса", "description": "Объясняет свой ход мыслей, делится промежуточными результатами", "weight": 7, "category": "basic"},
            {"name": "Приукрашивание", "description": "Завышает свои достижения, преувеличивает опыт", "weight": 8, "category": "red_flags"},
            {"name": "Противоречия в словах", "description": "Говорит разное в разных ситуациях, ловится на несоответствиях", "weight": 9, "category": "red_flags"},
            {"name": "Уход от ответа", "description": "Отвечает не на тот вопрос, меняет тему", "weight": 7, "category": "red_flags"},
        ],
    },
    {
        "name": "Обучаемость и развитие",
        "description": "Способность учиться и расти профессионально",
        "criteria": [
            {"name": "Скорость освоения", "description": "Быстро схватывает новые концепции, применяет на практике", "weight": 8, "category": "potential"},
            {"name": "Обратная связь", "description": "Принимает критику конструктивно, внедряет улучшения", "weight": 8, "category": "green_flags"},
            {"name": "Любознательность", "description": "Задаёт вопросы, интересуется смежными темами", "weight": 7, "category": "green_flags"},
            {"name": "Те же грабли", "description": "Повторяет одни и те же ошибки, не делает выводов", "weight": 9, "category": "red_flags"},
            {"name": "Защитная реакция", "description": "Воспринимает критику как атаку, оправдывается вместо исправления", "weight": 8, "category": "red_flags"},
            {"name": "Зона комфорта", "description": "Избегает новых задач, держится за знакомое", "weight": 7, "category": "red_flags"},
            {"name": "Самообучение", "description": "Учится самостоятельно, не ждёт пока научат", "weight": 8, "category": "potential"},
        ],
    },
    {
        "name": "Ответственность и ownership",
        "description": "Отношение к работе и результатам",
        "criteria": [
            {"name": "Владение задачей", "description": "Доводит до конца, не бросает на полпути, отвечает за результат", "weight": 9, "category": "basic"},
            {"name": "Проактивность", "description": "Видит проблемы заранее, предлагает решения до того как спросят", "weight": 8, "category": "green_flags"},
            {"name": "Признание своих ошибок", "description": "Не перекладывает вину, берёт ответственность на себя", "weight": 8, "category": "green_flags"},
            {"name": "Футбол задачами", "description": "Перекидывает задачи другим, ищет причины не делать", "weight": 8, "category": "red_flags"},
            {"name": "Виноваты все кроме меня", "description": "Всегда находит внешние причины неудач", "weight": 9, "category": "red_flags"},
            {"name": "Формальный подход", "description": "Делает минимум, только чтобы отстали", "weight": 7, "category": "red_flags"},
        ],
    },
]


def get_universal_presets() -> List[Dict[str, Any]]:
    """Get universal preset templates that work across all chat types."""
    return UNIVERSAL_PRESETS


def get_system_prompt_for_type(chat_type: str, custom_description: str = None) -> str:
    """Get AI system prompt based on chat type."""
    config = get_chat_type_config(chat_type)

    base_prompts = {
        "hr": """You are an HR expert analyzing candidate conversations. Focus on:
- Evaluating soft and hard skills demonstrated
- Identifying red flags and green flags
- Assessing cultural fit and communication style
- Providing hiring recommendations with confidence levels""",

        "project": """You are a project manager analyzing team communications. Focus on:
- Tracking task progress and blockers
- Identifying responsibility assignments
- Monitoring deadline risks
- Summarizing decisions and action items""",

        "client": """You are a customer success manager analyzing client communications. Focus on:
- Assessing client satisfaction and sentiment
- Tracking requests and our commitments
- Identifying churn risks early
- Finding upsell opportunities""",

        "contractor": """You are a vendor manager evaluating contractor communications. Focus on:
- Assessing work quality and reliability
- Tracking deadline adherence
- Evaluating communication quality
- Recommending continuation or changes""",

        "sales": """You are a sales analyst reviewing prospect conversations. Focus on:
- Determining deal stage and progression
- Identifying objections and concerns
- Extracting budget and timeline info
- Finding decision makers and champions""",

        "support": """You are a support quality analyst reviewing customer interactions. Focus on:
- Categorizing and summarizing issues
- Measuring resolution effectiveness
- Tracking response times
- Identifying recurring problems""",

        "custom": f"""You are an AI analyst reviewing conversations. {custom_description or 'Provide comprehensive analysis based on the context.'}""",
    }

    return base_prompts.get(chat_type, base_prompts["custom"])
