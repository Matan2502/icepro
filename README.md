# 🧊 IcePro — פלטפורמת ניהול עסק קרח

מערכת ווב לניהול מלאי, אירועים ורווחיות לעסק מכירת שקיות קרח.

---

## 📁 מבנה הקבצים

```
icepro/
├── app.py              ← שרת Flask — כל ה-routes וה-API
├── database.py         ← חיבור ל-SQLite, יצירת טבלאות, seed data
├── icepro.db           ← קובץ מסד הנתונים (נוצר אוטומטית בהרצה ראשונה)
├── requirements.txt    ← תלויות Python
├── templates/
│   ├── base.html       ← תבנית בסיס עם sidebar ו-modal
│   ├── dashboard.html  ← דשבורד ראשי
│   ├── inventory.html  ← ניהול מלאי ומקררים
│   ├── events.html     ← ניהול אירועים
│   └── profit.html     ← מסך רווחיות
└── static/
    ├── css/style.css   ← כל העיצוב
    └── js/main.js      ← לוגיקת modal
```

---

## ⚡ הרצה מהירה

### דרישות מוקדמות
- Python 3.9+

### התקנה והרצה

```bash
# 1. כנס לתיקיית הפרויקט
cd icepro

# 2. צור סביבה וירטואלית (מומלץ)
python -m venv venv
source venv/bin/activate        # Mac / Linux
venv\Scripts\activate           # Windows

# 3. התקן תלויות
pip install -r requirements.txt

# 4. הפעל את השרת
python app.py
```

פתח דפדפן על: **http://127.0.0.1:5000**

---

## 🗄️ מסד הנתונים (SQL)

המערכת משתמשת ב-**SQLite** — קובץ `icepro.db` שנוצר אוטומטית.

### טבלאות

#### `fridges` — מקררים
| עמודה     | סוג     | תיאור              |
|-----------|---------|---------------------|
| id        | INTEGER | מזהה ייחודי (PK)    |
| name      | TEXT    | שם המקרר            |
| location  | TEXT    | מיקום (עיר)         |
| capacity  | INTEGER | קיבולת מקסימלית     |
| created_at| TEXT    | תאריך יצירה         |

#### `inventory` — מלאי נוכחי
| עמודה      | סוג     | תיאור               |
|------------|---------|----------------------|
| id         | INTEGER | מזהה ייחודי          |
| fridge_id  | INTEGER | FK → fridges         |
| quantity   | INTEGER | כמות שקיות נוכחית    |
| updated_at | TEXT    | עדכון אחרון          |

#### `events` — אירועים
| עמודה         | סוג    | תיאור                         |
|---------------|--------|-------------------------------|
| id            | INTEGER| מזהה ייחודי                   |
| name          | TEXT   | שם האירוע                     |
| event_date    | TEXT   | תאריך (YYYY-MM-DD)            |
| fridge_id     | INTEGER| FK → fridges                  |
| quantity      | INTEGER| כמות שקיות                    |
| price         | REAL   | מחיר ללקוח (₪)                |
| cost_per_unit | REAL   | עלות ליחידה (ברירת מחדל: 3.5) |
| status        | TEXT   | pending / active / done       |
| notes         | TEXT   | הערות אופציונליות             |

#### `inventory_log` — לוג תנועות מלאי
| עמודה      | סוג     | תיאור                    |
|------------|---------|--------------------------|
| id         | INTEGER | מזהה ייחודי              |
| fridge_id  | INTEGER | FK → fridges             |
| change     | INTEGER | שינוי בכמות (+/-)        |
| reason     | TEXT    | סיבה                     |
| event_id   | INTEGER | FK → events (אופציונלי)  |
| created_at | TEXT    | תאריך ושעה               |

#### `expenses` — הוצאות
| עמודה        | סוג    | תיאור                              |
|--------------|--------|------------------------------------|
| id           | INTEGER| מזהה ייחודי                        |
| description  | TEXT   | תיאור ההוצאה                       |
| amount       | REAL   | סכום (₪)                           |
| category     | TEXT   | supply / logistics / maintenance / general |
| expense_date | TEXT   | תאריך ההוצאה                       |

---

## 🔌 API Endpoints

| Method | URL                          | תיאור                    |
|--------|------------------------------|--------------------------|
| POST   | `/api/stock/add`             | הוסף מלאי למקרר          |
| POST   | `/api/stock/transfer`        | העבר מלאי בין מקררים     |
| POST   | `/api/events/add`            | צור אירוע חדש            |
| POST   | `/api/events/<id>/status`    | עדכן סטטוס אירוע         |
| POST   | `/api/expenses/add`          | הוסף הוצאה               |
| POST   | `/api/fridges/add`           | הוסף מקרר חדש            |

### דוגמאות

```bash
# הוספת מלאי
curl -X POST http://localhost:5000/api/stock/add \
  -H "Content-Type: application/json" \
  -d '{"fridge_id": 1, "quantity": 100, "reason": "קבלת סחורה"}'

# יצירת אירוע
curl -X POST http://localhost:5000/api/events/add \
  -H "Content-Type: application/json" \
  -d '{"name": "חתונה רמת גן", "event_date": "2026-05-01", "fridge_id": 1, "quantity": 200, "price": 2000, "cost_per_unit": 3.5}'

# סימון אירוע כהושלם (מוריד מלאי אוטומטית)
curl -X POST http://localhost:5000/api/events/1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "done"}'
```

---

## 📊 מסכים

| מסך         | URL          | תיאור                                        |
|-------------|--------------|----------------------------------------------|
| דשבורד      | `/`          | סיכום מלאי, אירועים קרובים, התראות           |
| מלאי        | `/inventory` | מקררים, כמויות, העברות, היסטוריית תנועות     |
| אירועים     | `/events`    | כל האירועים, פילטרים, עדכון סטטוס            |
| רווחיות     | `/profit`    | הכנסות/עלויות/רווח לפי חודש, גרף, הוצאות    |

---

## 🔧 התאמות נפוצות

### שינוי עלות ברירת מחדל לשקית
בקובץ `database.py`, שנה את הערך `3.5` בנתוני ה-seed:
```python
cost_per_unit = 3.5  # ← שנה לעלות האמיתית שלך
```

### הוספת שדה חדש לטבלה
ערוך את `database.py` בפונקציה `init_db()` — הוסף עמודה ב-SQL ועדכן את הטפסים ב-HTML בהתאם.

### מחיקת כל הנתונים (התחלה מחדש)
פשוט מחק את `icepro.db` והפעל מחדש — הטבלאות ייוצרו מחדש עם נתוני דמה.

---

## 🚀 שדרוגים עתידיים מומלצים

- [ ] התחברות עם סיסמה לכל שותף
- [ ] ייצוא דוחות ל-Excel
- [ ] גרפים חודשיים עם Chart.js
- [ ] אפליקציית אנדרואיד (Flask API + Android Studio)
- [ ] העלאה לשרת (Render / Railway — חינמי)

---

בנוי עם Python + Flask + SQLite + HTML/CSS/JS
