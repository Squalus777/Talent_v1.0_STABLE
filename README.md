# ⭐ Talent App (Commercial Edition)

**Talent App** is a robust, data-driven Talent Management System designed to streamline performance reviews, goal setting, and employee development. Built with **Streamlit** and **Python**, it offers a complete suite of tools for HR professionals, managers, and employees.

---

## 🚀 Key Features

### 1. Performance Management
* **9-Box Matrix:** Visual talent mapping based on Performance vs. Potential.
* **Snail Trail Analytics:** Historical tracking of employee movement within the 9-box matrix over time.
* **Gap Analysis:** Visual comparison between Employee Self-Evaluation and Manager Evaluation to identify perception gaps.
* **Draft & Lock:** Secure workflow allowing managers to save drafts before submitting final, locked reviews.

### 2. Goal Management (MBO)
* **Weighted Goals:** Logic ensures total goal weight equals exactly 100%.
* **KPI Tracking:** Detailed KPI editor for every goal.
* **Progress Tracking:** Visual progress bars and status updates.

### 3. Individual Development Plans (IDP)
* **70-20-10 Model:** Structured development planning covering Experience (70%), Mentoring (20%), and Education (10%).
* **Career Goals:** Diagnostic tools for strengths, areas for improvement, and career aspirations.

### 4. Role-Based Access Control (RBAC)
* **Super Admin:** System configuration, user management, backups, and period settings.
* **HR:** Organization-wide analytics, form designer, and reporting.
* **Manager:** Team dashboards, evaluations, and approval workflows.
* **Employee:** Self-service portal for goals, IDP, and self-evaluations.

---

## 🛠️ Technology Stack

* **Frontend/Backend:** Python (Streamlit)
* **Database:** SQLite (Lightweight, robust, JSON-compatible)
* **Visualization:** Plotly Express & Graph Objects
* **Data Manipulation:** Pandas

---

## 📦 Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/YourUsername/talent-app.git](https://github.com/YourUsername/talent-app.git)
    cd talent-app
    ```

2.  **Create a virtual environment (Recommended):**
    ```bash
    python -m venv venv
    # Windows:
    venv\Scripts\activate
    # Mac/Linux:
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    streamlit run main.py
    ```

---

## 🔑 Default Credentials (First Run)

The system automatically initializes with a Super Admin account:

* **Username:** `admin`
* **Password:** `admin123`

*Note: Please change the admin password immediately after the first login via the Admin Console.*

---

## 📂 Project Structure

```text
talent-app/
├── main.py              # Application entry point & Routing
├── auth.py              # Authentication logic
├── modules/
│   ├── database.py      # Database connections, Init, & Migrations
│   ├── utils.py         # Helper functions, Hashing, Metrics
│   ├── views_admin.py   # Super Admin interface
│   ├── views_hr.py      # HR Analytics & Settings
│   ├── views_mgr.py     # Manager Workflow (Evaluations, Team)
│   └── views_emp.py     # Employee Self-Service
└── talent_database.db   # SQLite Database (Created on first run)
