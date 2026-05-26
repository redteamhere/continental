"""
Translations for EscrowBot in 5 languages.
Keys are used throughout handlers and keyboards.
"""
from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    # ── English ──────────────────────────────────────────────
    "en": {
        "flag":             "🇺🇸 English",
        "choose_language":  "🌍 <b>Welcome to EscrowBot!</b>\n\nPlease choose your language:",

        "welcome_new": (
            "👋 <b>Welcome to EscrowBot!</b>\n\n"
            "I'm a secure escrow service for crypto transactions.\n\n"
            "🔒 <b>How it works:</b>\n"
            "1. Buyer creates a deal and funds it\n"
            "2. Seller completes the work\n"
            "3. Buyer releases funds — or opens a dispute\n\n"
            "⚠️ This bot will NEVER ask for your private keys or seed phrases."
        ),
        "welcome_back":     "👋 Welcome back, <b>{name}</b>!\n\nWhat would you like to do today?",
        "create_pin":       "🔐 <b>Create your PIN</b>\n\nTap the button below to set a secure 4–8 digit PIN.",
        "pin_reset":        "🔑 <b>PIN Required</b>\n\nYour PIN was reset. Please set a new PIN to continue.",
        "account_created":  "🎉 <b>Account created!</b>\n\nReferral code: <code>{referral_code}</code>\n\nYou're all set — explore the menu below.",
        "language_changed": "✅ Language changed to English.",

        # Main menu buttons
        "btn_new_deal":   "📋 New Deal",
        "btn_my_deals":   "📁 My Deals",
        "btn_profile":    "👤 Profile",
        "btn_wallet":     "💰 Wallet",
        "btn_stats":      "📊 Statistics",
        "btn_referral":   "🔗 Referral",
        "btn_help":       "ℹ️ Help",
        "btn_back":       "⬅️ Back",
        "btn_language":   "🌍 Language",
        "btn_change_pin": "🔑 Change PIN",
        "btn_set_pin":    "🔒 Set PIN",

        # Profile page
        "profile_title":        "Your Profile",
        "profile_name":         "Name",
        "profile_username":     "Username",
        "profile_member_since": "Member since",
        "profile_no_pin":       "⚠️ No PIN set",
        "profile_stats":        "Statistics",
        "profile_total_deals":  "Total Deals",
        "profile_purchases":    "Purchases",
        "profile_sales":        "Sales",
        "profile_reputation":   "Reputation",
        "profile_referral":     "Referral",
        "profile_your_code":    "Your code",
        "profile_security":     "Security",
        "profile_pin":          "PIN",
        "role_admin":           "Admin",
        "role_moderator":       "Moderator",
        "role_user":            "User",

        # Stats page
        "stats_title":          "📊 Your Statistics",
        "stats_total_deals":    "Total Deals",
        "stats_purchases":      "Purchases",
        "stats_sales":          "Sales",
        "stats_disputes_open":  "Disputes Opened",
        "stats_disputes_won":   "Disputes Won",
        "stats_reputation":     "⭐ Reputation",

        # Referral page
        "referral_title":       "🔗 Referral Program",
        "referral_desc":        "Share your link and earn <b>{bonus}% bonus</b> on each deal your referrals make.",
        "referral_your_code":   "Your code",
        "referral_your_link":   "Your link",

        # PIN management
        "pin_set_title":        "🔒 <b>Set your PIN</b>\n\nTap the button below to set a 4–8 digit PIN.",
        "pin_change_title":     "🔐 <b>Change PIN</b>\n\nFirst, enter your <b>current</b> PIN to verify it's you.",
        "pin_verified":         "✅ Verified. Now set your new PIN.",
        "pin_new_title":        "🔑 <b>New PIN</b>\n\nTap the button to set your new PIN.",
        "pin_wrong":            "❌ Wrong PIN. Try again:",
    },

    # ── Chinese (Simplified) ─────────────────────────────────
    "zh": {
        "flag":             "🇨🇳 中文",
        "choose_language":  "🌍 <b>欢迎来到 EscrowBot！</b>\n\n请选择您的语言：",

        "welcome_new": (
            "👋 <b>欢迎来到 EscrowBot！</b>\n\n"
            "我是一个安全的加密货币交易担保服务。\n\n"
            "🔒 <b>工作原理：</b>\n"
            "1. 买家创建交易并提供资金\n"
            "2. 卖家完成工作\n"
            "3. 买家释放资金 — 或发起争议\n\n"
            "⚠️ 本机器人绝不会要求您提供私钥或助记词。"
        ),
        "welcome_back":     "👋 欢迎回来，<b>{name}</b>！\n\n今天您想做什么？",
        "create_pin":       "🔐 <b>创建您的 PIN 码</b>\n\n点击下方按钮设置 4–8 位数字 PIN 码。",
        "pin_reset":        "🔑 <b>需要 PIN 码</b>\n\n您的 PIN 码已被重置，请设置新 PIN 码以继续。",
        "account_created":  "🎉 <b>账户已创建！</b>\n\n推荐码：<code>{referral_code}</code>\n\n一切就绪，探索菜单吧。",
        "language_changed": "✅ 语言已更改为中文。",

        "btn_new_deal":   "📋 新交易",
        "btn_my_deals":   "📁 我的交易",
        "btn_profile":    "👤 个人资料",
        "btn_wallet":     "💰 钱包",
        "btn_stats":      "📊 统计",
        "btn_referral":   "🔗 推荐",
        "btn_help":       "ℹ️ 帮助",
        "btn_back":       "⬅️ 返回",
        "btn_language":   "🌍 语言",
        "btn_change_pin": "🔑 修改 PIN 码",
        "btn_set_pin":    "🔒 设置 PIN 码",

        "profile_title":        "个人资料",
        "profile_name":         "姓名",
        "profile_username":     "用户名",
        "profile_member_since": "注册时间",
        "profile_no_pin":       "⚠️ 未设置 PIN 码",
        "profile_stats":        "统计数据",
        "profile_total_deals":  "总交易数",
        "profile_purchases":    "购买",
        "profile_sales":        "销售",
        "profile_reputation":   "信誉",
        "profile_referral":     "推荐",
        "profile_your_code":    "您的推荐码",
        "profile_security":     "安全",
        "profile_pin":          "PIN 码",
        "profile_no_pin":       "⚠️ 未设置 PIN 码",
        "role_admin":           "管理员",
        "role_moderator":       "版主",
        "role_user":            "用户",

        "stats_title":          "📊 您的统计数据",
        "stats_total_deals":    "总交易数",
        "stats_purchases":      "购买",
        "stats_sales":          "销售",
        "stats_disputes_open":  "发起的争议",
        "stats_disputes_won":   "赢得的争议",
        "stats_reputation":     "⭐ 信誉",

        "referral_title":       "🔗 推荐计划",
        "referral_desc":        "分享您的链接，每笔推荐交易可获得 <b>{bonus}% 奖励</b>。",
        "referral_your_code":   "您的推荐码",
        "referral_your_link":   "您的链接",

        "pin_set_title":        "🔒 <b>设置 PIN 码</b>\n\n点击下方按钮设置 4–8 位数字 PIN 码。",
        "pin_change_title":     "🔐 <b>修改 PIN 码</b>\n\n首先输入您的<b>当前</b> PIN 码进行验证。",
        "pin_verified":         "✅ 验证成功，请设置新 PIN 码。",
        "pin_new_title":        "🔑 <b>新 PIN 码</b>\n\n点击按钮设置您的新 PIN 码。",
        "pin_wrong":            "❌ PIN 码错误，请重试：",
    },

    # ── Russian ──────────────────────────────────────────────
    "ru": {
        "flag":             "🇷🇺 Русский",
        "choose_language":  "🌍 <b>Добро пожаловать в EscrowBot!</b>\n\nПожалуйста, выберите язык:",

        "welcome_new": (
            "👋 <b>Добро пожаловать в EscrowBot!</b>\n\n"
            "Я — безопасный эскроу-сервис для крипто-транзакций.\n\n"
            "🔒 <b>Как это работает:</b>\n"
            "1. Покупатель создаёт сделку и вносит средства\n"
            "2. Продавец выполняет работу\n"
            "3. Покупатель освобождает средства — или открывает спор\n\n"
            "⚠️ Бот НИКОГДА не запрашивает приватные ключи или сид-фразы."
        ),
        "welcome_back":     "👋 С возвращением, <b>{name}</b>!\n\nЧто хотите сделать сегодня?",
        "create_pin":       "🔐 <b>Создайте PIN-код</b>\n\nНажмите кнопку ниже, чтобы задать 4–8-значный PIN.",
        "pin_reset":        "🔑 <b>Требуется PIN-код</b>\n\nВаш PIN был сброшен. Создайте новый, чтобы продолжить.",
        "account_created":  "🎉 <b>Аккаунт создан!</b>\n\nРеферальный код: <code>{referral_code}</code>\n\nВсё готово — изучите меню ниже.",
        "language_changed": "✅ Язык изменён на Русский.",

        "btn_new_deal":   "📋 Новая сделка",
        "btn_my_deals":   "📁 Мои сделки",
        "btn_profile":    "👤 Профиль",
        "btn_wallet":     "💰 Кошелёк",
        "btn_stats":      "📊 Статистика",
        "btn_referral":   "🔗 Реферал",
        "btn_help":       "ℹ️ Помощь",
        "btn_back":       "⬅️ Назад",
        "btn_language":   "🌍 Язык",
        "btn_change_pin": "🔑 Изменить PIN",
        "btn_set_pin":    "🔒 Установить PIN",

        "profile_title":        "Ваш профиль",
        "profile_name":         "Имя",
        "profile_username":     "Имя пользователя",
        "profile_member_since": "Участник с",
        "profile_no_pin":       "⚠️ PIN не установлен",
        "profile_stats":        "Статистика",
        "profile_total_deals":  "Всего сделок",
        "profile_purchases":    "Покупки",
        "profile_sales":        "Продажи",
        "profile_reputation":   "Репутация",
        "profile_referral":     "Реферал",
        "profile_your_code":    "Ваш код",
        "profile_security":     "Безопасность",
        "profile_pin":          "PIN",
        "role_admin":           "Администратор",
        "role_moderator":       "Модератор",
        "role_user":            "Пользователь",

        "stats_title":          "📊 Ваша статистика",
        "stats_total_deals":    "Всего сделок",
        "stats_purchases":      "Покупки",
        "stats_sales":          "Продажи",
        "stats_disputes_open":  "Открыто споров",
        "stats_disputes_won":   "Выиграно споров",
        "stats_reputation":     "⭐ Репутация",

        "referral_title":       "🔗 Реферальная программа",
        "referral_desc":        "Поделитесь ссылкой и получайте <b>{bonus}% бонус</b> с каждой сделки ваших рефералов.",
        "referral_your_code":   "Ваш код",
        "referral_your_link":   "Ваша ссылка",

        "pin_set_title":        "🔒 <b>Установите PIN-код</b>\n\nНажмите кнопку ниже, чтобы задать 4–8-значный PIN.",
        "pin_change_title":     "🔐 <b>Изменить PIN</b>\n\nСначала введите <b>текущий</b> PIN для подтверждения.",
        "pin_verified":         "✅ Подтверждено. Теперь задайте новый PIN.",
        "pin_new_title":        "🔑 <b>Новый PIN</b>\n\nНажмите кнопку, чтобы задать новый PIN.",
        "pin_wrong":            "❌ Неверный PIN. Попробуйте ещё раз:",
    },

    # ── Brazilian Portuguese ──────────────────────────────────
    "pt": {
        "flag":             "🇧🇷 Português",
        "choose_language":  "🌍 <b>Bem-vindo ao EscrowBot!</b>\n\nPor favor, escolha seu idioma:",

        "welcome_new": (
            "👋 <b>Bem-vindo ao EscrowBot!</b>\n\n"
            "Sou um serviço de garantia seguro para transações cripto.\n\n"
            "🔒 <b>Como funciona:</b>\n"
            "1. Comprador cria um negócio e faz o pagamento\n"
            "2. Vendedor conclui o trabalho\n"
            "3. Comprador libera os fundos — ou abre uma disputa\n\n"
            "⚠️ Este bot NUNCA solicitará suas chaves privadas ou frases-semente."
        ),
        "welcome_back":     "👋 Bem-vindo de volta, <b>{name}</b>!\n\nO que você gostaria de fazer hoje?",
        "create_pin":       "🔐 <b>Crie seu PIN</b>\n\nToque no botão abaixo para definir um PIN de 4–8 dígitos.",
        "pin_reset":        "🔑 <b>PIN necessário</b>\n\nSeu PIN foi redefinido. Por favor, crie um novo PIN para continuar.",
        "account_created":  "🎉 <b>Conta criada!</b>\n\nCódigo de referência: <code>{referral_code}</code>\n\nTudo pronto — explore o menu abaixo.",
        "language_changed": "✅ Idioma alterado para Português.",

        "btn_new_deal":   "📋 Novo Negócio",
        "btn_my_deals":   "📁 Meus Negócios",
        "btn_profile":    "👤 Perfil",
        "btn_wallet":     "💰 Carteira",
        "btn_stats":      "📊 Estatísticas",
        "btn_referral":   "🔗 Indicação",
        "btn_help":       "ℹ️ Ajuda",
        "btn_back":       "⬅️ Voltar",
        "btn_language":   "🌍 Idioma",
        "btn_change_pin": "🔑 Alterar PIN",
        "btn_set_pin":    "🔒 Definir PIN",

        "profile_title":        "Seu Perfil",
        "profile_name":         "Nome",
        "profile_username":     "Usuário",
        "profile_member_since": "Membro desde",
        "profile_no_pin":       "⚠️ PIN não definido",
        "profile_stats":        "Estatísticas",
        "profile_total_deals":  "Total de Negócios",
        "profile_purchases":    "Compras",
        "profile_sales":        "Vendas",
        "profile_reputation":   "Reputação",
        "profile_referral":     "Indicação",
        "profile_your_code":    "Seu código",
        "profile_security":     "Segurança",
        "profile_pin":          "PIN",
        "role_admin":           "Administrador",
        "role_moderator":       "Moderador",
        "role_user":            "Usuário",

        "stats_title":          "📊 Suas Estatísticas",
        "stats_total_deals":    "Total de Negócios",
        "stats_purchases":      "Compras",
        "stats_sales":          "Vendas",
        "stats_disputes_open":  "Disputas Abertas",
        "stats_disputes_won":   "Disputas Ganhas",
        "stats_reputation":     "⭐ Reputação",

        "referral_title":       "🔗 Programa de Indicação",
        "referral_desc":        "Compartilhe seu link e ganhe <b>{bonus}% de bônus</b> em cada negócio dos seus indicados.",
        "referral_your_code":   "Seu código",
        "referral_your_link":   "Seu link",

        "pin_set_title":        "🔒 <b>Defina seu PIN</b>\n\nToque no botão abaixo para definir um PIN de 4–8 dígitos.",
        "pin_change_title":     "🔐 <b>Alterar PIN</b>\n\nPrimeiro, insira seu PIN <b>atual</b> para verificar.",
        "pin_verified":         "✅ Verificado. Agora defina seu novo PIN.",
        "pin_new_title":        "🔑 <b>Novo PIN</b>\n\nToque no botão para definir seu novo PIN.",
        "pin_wrong":            "❌ PIN incorreto. Tente novamente:",
    },

    # ── Turkish ──────────────────────────────────────────────
    "tr": {
        "flag":             "🇹🇷 Türkçe",
        "choose_language":  "🌍 <b>EscrowBot'a Hoş Geldiniz!</b>\n\nLütfen dilinizi seçin:",

        "welcome_new": (
            "👋 <b>EscrowBot'a Hoş Geldiniz!</b>\n\n"
            "Kripto işlemleri için güvenli bir emanet hizmetiyim.\n\n"
            "🔒 <b>Nasıl çalışır:</b>\n"
            "1. Alıcı bir anlaşma oluşturur ve fonlar\n"
            "2. Satıcı işi tamamlar\n"
            "3. Alıcı fonları serbest bırakır — veya uyuşmazlık açar\n\n"
            "⚠️ Bu bot hiçbir zaman özel anahtarlarınızı veya tohum ifadelerinizi istemez."
        ),
        "welcome_back":     "👋 Tekrar hoş geldiniz, <b>{name}</b>!\n\nBugün ne yapmak istersiniz?",
        "create_pin":       "🔐 <b>PIN'inizi oluşturun</b>\n\nGüvenli bir 4–8 haneli PIN ayarlamak için aşağıdaki butona dokunun.",
        "pin_reset":        "🔑 <b>PIN gerekli</b>\n\nPIN'iniz sıfırlandı. Devam etmek için lütfen yeni bir PIN oluşturun.",
        "account_created":  "🎉 <b>Hesap oluşturuldu!</b>\n\nReferans kodunuz: <code>{referral_code}</code>\n\nHazırsınız — aşağıdaki menüyü keşfedin.",
        "language_changed": "✅ Dil Türkçe olarak değiştirildi.",

        "btn_new_deal":   "📋 Yeni Anlaşma",
        "btn_my_deals":   "📁 Anlaşmalarım",
        "btn_profile":    "👤 Profil",
        "btn_wallet":     "💰 Cüzdan",
        "btn_stats":      "📊 İstatistikler",
        "btn_referral":   "🔗 Referans",
        "btn_help":       "ℹ️ Yardım",
        "btn_back":       "⬅️ Geri",
        "btn_language":   "🌍 Dil",
        "btn_change_pin": "🔑 PIN Değiştir",
        "btn_set_pin":    "🔒 PIN Ayarla",

        "profile_title":        "Profiliniz",
        "profile_name":         "Ad",
        "profile_username":     "Kullanıcı adı",
        "profile_member_since": "Üyelik tarihi",
        "profile_no_pin":       "⚠️ PIN ayarlanmamış",
        "profile_stats":        "İstatistikler",
        "profile_total_deals":  "Toplam Anlaşma",
        "profile_purchases":    "Alımlar",
        "profile_sales":        "Satışlar",
        "profile_reputation":   "İtibar",
        "profile_referral":     "Referans",
        "profile_your_code":    "Kodunuz",
        "profile_security":     "Güvenlik",
        "profile_pin":          "PIN",
        "role_admin":           "Yönetici",
        "role_moderator":       "Moderatör",
        "role_user":            "Kullanıcı",

        "stats_title":          "📊 İstatistikleriniz",
        "stats_total_deals":    "Toplam Anlaşma",
        "stats_purchases":      "Alımlar",
        "stats_sales":          "Satışlar",
        "stats_disputes_open":  "Açılan Uyuşmazlıklar",
        "stats_disputes_won":   "Kazanılan Uyuşmazlıklar",
        "stats_reputation":     "⭐ İtibar",

        "referral_title":       "🔗 Referans Programı",
        "referral_desc":        "Bağlantınızı paylaşın, referanslarınızın her anlaşmasından <b>{bonus}% bonus</b> kazanın.",
        "referral_your_code":   "Kodunuz",
        "referral_your_link":   "Bağlantınız",

        "pin_set_title":        "🔒 <b>PIN'inizi ayarlayın</b>\n\n4–8 haneli PIN ayarlamak için aşağıdaki butona dokunun.",
        "pin_change_title":     "🔐 <b>PIN Değiştir</b>\n\nÖnce kimliğinizi doğrulamak için <b>mevcut</b> PIN'inizi girin.",
        "pin_verified":         "✅ Doğrulandı. Şimdi yeni PIN'inizi ayarlayın.",
        "pin_new_title":        "🔑 <b>Yeni PIN</b>\n\nYeni PIN'inizi ayarlamak için butona dokunun.",
        "pin_wrong":            "❌ Yanlış PIN. Tekrar deneyin:",
    },
}

SUPPORTED_LANGUAGES = list(STRINGS.keys())   # ["en", "zh", "ru", "pt", "tr"]


def t(key: str, lang: str = "en", **kwargs) -> str:
    """
    Translate key to the given language. Falls back to English if
    the key or language is not found.  Supports .format() substitutions.
    """
    lang = lang if lang in STRINGS else "en"
    text = STRINGS[lang].get(key) or STRINGS["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text


def get_lang(user) -> str:
    """Return user's language code, defaulting to 'en'."""
    if user is None:
        return "en"
    code = getattr(user, "language_code", "en") or "en"
    return code if code in STRINGS else "en"
