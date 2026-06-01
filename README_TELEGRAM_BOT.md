# Telegram Novel Publishing Bot

هذا المشروع يحتوي على بوت نشر تلقائي لفصول روايات باستخدام `python-telegram-bot` و `aiohttp` و `sqlite3`.

## الملفات

- `main.py`: الكود الكامل للبوت.
- `requirements.txt`: المكتبات المطلوبة.
- `README_TELEGRAM_BOT.md`: تعليمات الإعداد والتشغيل.

## متطلبات البيئة

أضف المتغيرات التالية في إعدادات Railway أو النظام:

- `BOT_TOKEN`: توكن البوت من BotFather.
- `ADMIN_ID`: رقم الآيدي الخاص بالأدمن.
- `CHANNEL_ID`: آيدي القناة أو اسم المستخدم الخاص بها.
- `PORT`: يقرأ البوت هذا المتغير تلقائيًا.

## كيفية التشغيل

1. ثبت المتطلبات:

```bash
pip install -r requirements.txt
```

2. شغّل البوت محلياً:

```bash
python main.py
```

## النشر على Railway

1. أنشئ مشروع جديد في Railway واختر مستودع Git أو ارفع المجلد.
2. تأكد من وجود الملفات التالية في جذر المشروع:
   - `main.py`
   - `requirements.txt`
   - `Procfile`
   - `runtime.txt`
3. في إعدادات البيئة (`Environment Variables`) أضف:
   - `BOT_TOKEN`
   - `ADMIN_ID`
   - `CHANNEL_ID`
4. Railway سيستخدم `PORT` تلقائياً، والكود يقرأ هذا المتغير للـ Health Check.
5. ابدأ التطبيق، وسيعمل البوت بشكل تلقائي.

## ملاحظات

- لا يستخدم هذا البوت مكتبة `apscheduler`.
- يعتمد على حلقة خلفية ذكية تتفقد الوقت كل 30 ثانية.
- الشاشة متاحة فقط للأدمن المحدد في `ADMIN_ID`.
- يوجد خادم صحة بسيط (`/health`) لضمان عمل البوت على Railway.
