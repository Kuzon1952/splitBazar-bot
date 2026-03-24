# 🛒 SplitBazar — Smart Shared Expense Tracker Bot

A Telegram bot for tracking shared expenses in groups. 
Perfect for roommates, dormitories, and shared living.

## 👨‍💻 Developer
- **Name:** Ovi Md Shamin Yasir
- **University:** Peter the Great Saint Petersburg Polytechnic University (spbstu.ru)
- **Group:** 5130201/40001
- **Subject:** Digital Analytics
- **Year:** 2nd year, 2026

## 👨‍🏫 Supervisor
- **Name:** Vladimir Alexandrovich Mulyukha
- **Title:** PhD in Technical Sciences
- **Position:** Director — Higher School of AI Technologies, SPbSTU

---

## 🚀 Features

| Feature | Description |
|---------|-------------|
| 👥 Groups | Create/join groups with invite codes |
| ➕ Add Expense | Track shared, personal, or mixed expenses |
| 📊 View Report | See balances and who owes whom |
| ✏️ Edit Expense | Edit or soft-delete expenses with admin approval |
| 🎯 Budget Target | Set monthly budget with progress alerts |
| 📥 Download Report | Export as PDF or Excel |
| 🔔 Notifications | Inactivity, large expense, reset deadline alerts |
| 🚪 Member Leave | Leave/remove with admin approval |
| ⚙️ Settings | Full group management for admin and members |
| 📝 ToDo List | Shared shopping list with notifications |
| 💬 Group Chat | Send messages to all group members |
| 🔄 Reset System | Monthly reset with password protection |
| 💣 Delete Group | Permanent group deletion with confirmation |

---

## 🛠️ Tech Stack

- **Language:** Python 3.14
- **Framework:** python-telegram-bot 22.7
- **Database:** PostgreSQL 18
- **Libraries:**
  - `psycopg2-binary` — PostgreSQL connection
  - `python-dotenv` — Environment variables
  - `reportlab` — PDF generation
  - `openpyxl` — Excel generation
  - `apscheduler` — Scheduled notifications

---

## 📁 Project Structure
```
splitBazar-bot/
├── bot/
│   ├── main.py                 # Entry point
│   ├── handlers/
│   │   ├── start.py            # /start command
│   │   ├── group.py            # Group management
│   │   ├── expense.py          # Add expense
│   │   ├── report.py           # View report
│   │   ├── edit.py             # Edit expense
│   │   ├── target.py           # Budget target
│   │   ├── notifications.py    # Scheduled alerts
│   │   ├── leave.py            # Member leave/remove
│   │   ├── settings.py         # Settings menu
│   │   ├── todo.py             # ToDo list
│   │   ├── chat.py             # Group chat
│   │   └── reset.py            # Reset system
│   ├── database/
│   │   ├── connection.py       # DB connection
│   │   └── queries.py          # All SQL queries
│   └── utils/
│       ├── calculations.py     # Balance calculations
│       └── report_generator.py # PDF/Excel generator
├── migrations/
│   └── init.sql                # Database schema
├── .env                        # Environment variables
├── requirements.txt            # Dependencies
├── docker-compose.yml          # Docker setup
└── README.md                   # This file
```

---

## ⚙️ Installation

### 1. Clone the repository
```bash
git clone https://github.com/Kuzon1952/splitBazar-bot.git
cd splitBazar-bot
```

### 2. Create virtual environment
```bash
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
pip install "python-telegram-bot[job-queue]"
```

### 4. Set up PostgreSQL
```bash
psql -U postgres
CREATE DATABASE splitbazar;
\q
psql -U postgres -d splitbazar -f migrations/init.sql
```

### 5. Configure environment
Create `.env` file:
```
BOT_TOKEN=your_telegram_bot_token
DB_HOST=localhost
DB_PORT=5432
DB_NAME=splitbazar
DB_USER=postgres
DB_PASSWORD=your_password
```

### 6. Run the bot
```bash
venv\Scripts\python.exe -m bot.main
```

---

## 🗄️ Database Schema

| Table | Description |
|-------|-------------|
| users | Telegram users |
| groups | Expense groups |
| group_members | Group membership |
| expenses | Expense records |
| expense_splits | Split calculations |
| budget_targets | Monthly budgets |
| edit_requests | Edit approval requests |
| todo_items | Shopping list items |
| group_messages | Group chat messages |

---

## 📱 How to Use

### Creating a Group
1. Press **👥 My Groups**
2. Press **➕ Create Group**
3. Enter group name (must be unique)
4. Select currency
5. Set reset password
6. Set password hint
7. Share invite code with members

### Adding an Expense
1. Press **➕ Add Expense**
2. Select group
3. Select date (today/yesterday/earlier)
4. Choose type (Shared/Personal/Mixed)
5. Enter amount
6. Choose split method
7. Add description and receipt (optional)

### Viewing Report
1. Press **📊 View Report**
2. Select group
3. Choose period (Last 2 weeks/This month/Custom)
4. View balances and settlements
5. Download PDF or Excel

### Monthly Reset
1. At end of month go to **⚙️ Settings**
2. Select group → **🔄 Reset Group**
3. Enter reset password
4. Choose **📥 Download & Reset** or **🔄 Reset Only**
5. Final report sent to all members

---

## 🔐 Security Features

- Reset password required for group reset
- Password hint for recovery
- Soft delete (data kept 3 months)
- Admin approval for member edits
- Admin approval for member leave
- Type "DELETE" confirmation for group deletion
- 3-month force lock if no reset

---

## 🔔 Automated Notifications

| Notification | Trigger |
|-------------|---------|
| 😴 Inactivity | 3 days without expense |
| 💸 Large Expense | Expense over 1000 |
| 📅 Reset Deadline | 7 days before month end |
| 🔒 Force Lock | 3 months without reset |

---

## 📬 Contact

- **Developer:** @virtual786
- **GitHub:** https://github.com/Kuzon1952/splitBazar-bot

---

*SplitBazar — Making shared expenses simple! 🛒*