TOKEN_PACKS = [
    {
        "plan_id": "starter_pack",
        "title": "بسته ۵۰ هزار توکن",
        "tokens": 50000,
        "amount_toman": 49000,
    },
    {
        "plan_id": "pro_pack",
        "title": "بسته ۲۰۰ هزار توکن",
        "tokens": 200000,
        "amount_toman": 149000,
    },
    {
        "plan_id": "power_pack",
        "title": "بسته ۱ میلیون توکن",
        "tokens": 1000000,
        "amount_toman": 499000,
    },
]

SUBSCRIPTION_PLANS = [
    {
        "plan_id": "plus_monthly",
        "title": "اشتراک پلاس ماهانه",
        "monthly_token_quota": 300000,
        "amount_toman": 199000,
        "benefits": ["۳۰۰ هزار توکن ماهانه", "مناسب برای گفت‌وگوی روزانه", "فعال‌سازی فوری آزمایشی"],
    },
    {
        "plan_id": "pro_monthly",
        "title": "اشتراک پرو ماهانه",
        "monthly_token_quota": 1000000,
        "amount_toman": 499000,
        "benefits": ["۱ میلیون توکن ماهانه", "مناسب برای استفاده سنگین", "فعال‌سازی فوری آزمایشی"],
    },
]


def get_token_pack(plan_id: str) -> dict | None:
    return next((plan for plan in TOKEN_PACKS if plan["plan_id"] == plan_id), None)


def get_subscription_plan(plan_id: str) -> dict | None:
    return next((plan for plan in SUBSCRIPTION_PLANS if plan["plan_id"] == plan_id), None)
