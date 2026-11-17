import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

import mysql.connector

try: 
    from tkcalendar import DateEntry
except ImportError:
    DateEntry = None


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your-password",
}
DB_NAME = "expense_db"
DEFAULT_CATEGORIES = ["Food", "Transport", "Education", "Shopping", "Entertainment", "Others"]



class Database:
    def __init__(self):
        server = mysql.connector.connect(**DB_CONFIG)
        cur = server.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        cur.close()
        server.close()

        self.conn = mysql.connector.connect(database=DB_NAME, **DB_CONFIG)
        self.conn.autocommit = True
        self._run(
            """CREATE TABLE IF NOT EXISTS categories (
                name VARCHAR(50) PRIMARY KEY
            )"""
        )
        self._run(
            """CREATE TABLE IF NOT EXISTS transactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                type ENUM('Income', 'Expense') NOT NULL,
                date DATE NOT NULL,
                category VARCHAR(50) NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                description VARCHAR(255)
            )"""
        )
        for c in DEFAULT_CATEGORIES:
            self._run("INSERT IGNORE INTO categories (name) VALUES (%s)", (c,))

    def _run(self, sql, params=(), fetch=None):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        result = None
        if fetch == "all":
            result = cur.fetchall()
        elif fetch == "one":
            result = cur.fetchone()
        cur.close()
        return result

    def categories(self):
        return [r[0] for r in self._run("SELECT name FROM categories ORDER BY name", fetch="all")]

    def add(self, ttype, d, category, amount, desc):
        self._run(
            "INSERT INTO transactions (type, date, category, amount, description) "
            "VALUES (%s, %s, %s, %s, %s)",
            (ttype, d, category, amount, desc),
        )

    def update(self, tid, d, category, amount, desc):
        self._run(
            "UPDATE transactions SET date=%s, category=%s, amount=%s, description=%s WHERE id=%s",
            (d, category, amount, desc, tid),
        )

    def delete(self, tid):
        self._run("DELETE FROM transactions WHERE id = %s", (tid,))

    def search(self, text=""):
        like = f"%{text}%"
        return self._run(
            "SELECT id, type, date, category, amount, description FROM transactions "
            "WHERE description LIKE %s OR category LIKE %s OR type LIKE %s "
            "ORDER BY date DESC, id DESC",
            (like, like, like),
            fetch="all",
        )

    def recent(self, n=10):
        return self._run(
            "SELECT id, type, date, category, amount, description FROM transactions "
            "ORDER BY date DESC, id DESC LIMIT %s",
            (n,),
            fetch="all",
        )

    def totals(self):
        rows = self._run("SELECT type, SUM(amount) FROM transactions GROUP BY type", fetch="all")
        t = {"Income": 0.0, "Expense": 0.0}
        for ttype, total in rows:
            t[ttype] = float(total)
        return t



def make_date_widget(parent, var):
    if DateEntry:
        return DateEntry(parent, textvariable=var, date_pattern="yyyy-mm-dd", width=14)
    return ttk.Entry(parent, textvariable=var, width=16)


def validate(date_str, amount_str):
    """Returns (date, amount) or None after showing an error."""
    try:
        d = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        messagebox.showerror("Error", "Date must be in YYYY-MM-DD format.")
        return None
    try:
        amount = float(amount_str)
        if amount <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Error", "Amount must be a number greater than 0.")
        return None
    return d, amount


def fill_tree(tree, rows):
    tree.delete(*tree.get_children())
    for tid, ttype, d, cat, amt, desc in rows:
        tree.insert("", "end", values=(tid, ttype, d, cat, f"{float(amt):.2f}", desc or ""))


def make_tree(parent, height=12):
    cols = ("id", "type", "date", "category", "amount", "description")
    tree = ttk.Treeview(parent, columns=cols, show="headings", height=height)
    for c, w in zip(cols, (40, 70, 90, 100, 90, 300)):
        tree.heading(c, text=c.title())
        tree.column(c, width=w)
    tree.tag_configure("Income", foreground="#1a7f37")
    tree.tag_configure("Expense", foreground="#c62828")
    return tree



class App(tk.Tk):
    def __init__(self, db):
        super().__init__()
        self.title("Expense Tracker")
        self.geometry("820x540")
        self.db = db

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.build_dashboard()
        self.income_form = self.build_form("Income")
        self.expense_form = self.build_form("Expense")
        self.build_transactions()

        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.refresh_all())
        self.refresh_all()


    def build_dashboard(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Dashboard")

        top = ttk.Frame(f)
        top.pack(fill="x", pady=(0, 10))
        self.lbl_income = ttk.Label(top, font=("Arial", 13, "bold"), foreground="#1a7f37")
        self.lbl_expense = ttk.Label(top, font=("Arial", 13, "bold"), foreground="#c62828")
        self.lbl_balance = ttk.Label(top, font=("Arial", 13, "bold"))
        for lbl in (self.lbl_income, self.lbl_expense, self.lbl_balance):
            lbl.pack(side="left", expand=True)

        ttk.Label(f, text="Recent transactions").pack(anchor="w")
        self.dash_tree = make_tree(f, height=14)
        self.dash_tree.pack(fill="both", expand=True, pady=4)

    def refresh_dashboard(self):
        t = self.db.totals()
        balance = t["Income"] - t["Expense"]
        self.lbl_income.config(text=f"Total Income: ₹{t['Income']:.2f}")
        self.lbl_expense.config(text=f"Total Expenses: ₹{t['Expense']:.2f}")
        self.lbl_balance.config(
            text=f"Balance: ₹{balance:.2f}",
            foreground="#1a7f37" if balance >= 0 else "#c62828",
        )
        fill_tree_tagged(self.dash_tree, self.db.recent(10))


    def build_form(self, ttype):
        f = ttk.Frame(self.nb, padding=20)
        self.nb.add(f, text=f"Add {ttype}")

        vars_ = {
            "date": tk.StringVar(value=date.today().isoformat()),
            "category": tk.StringVar(),
            "amount": tk.StringVar(),
            "desc": tk.StringVar(),
        }
        row = 0
        ttk.Label(f, text="Date").grid(row=row, column=0, sticky="w", pady=6)
        make_date_widget(f, vars_["date"]).grid(row=row, column=1, sticky="w")

        combo = None
        if ttype == "Expense":
            row += 1
            ttk.Label(f, text="Category").grid(row=row, column=0, sticky="w", pady=6)
            combo = ttk.Combobox(f, textvariable=vars_["category"], state="readonly", width=20)
            combo.grid(row=row, column=1, sticky="w")

        row += 1
        ttk.Label(f, text="Amount (₹)").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(f, textvariable=vars_["amount"], width=22).grid(row=row, column=1, sticky="w")

        row += 1
        ttk.Label(f, text="Description").grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(f, textvariable=vars_["desc"], width=40).grid(row=row, column=1, sticky="w")

        row += 1
        ttk.Button(f, text=f"Save {ttype}",
                   command=lambda: self.save_new(ttype, vars_)).grid(row=row, column=1, sticky="w", pady=12)

        return {"vars": vars_, "combo": combo}

    def save_new(self, ttype, v):
        parsed = validate(v["date"].get(), v["amount"].get())
        if not parsed:
            return
        d, amount = parsed
        if ttype == "Expense":
            category = v["category"].get()
            if not category:
                messagebox.showerror("Error", "Select a category.")
                return
        else:
            category = "Income"
        try:
            self.db.add(ttype, d, category, amount, v["desc"].get().strip())
        except mysql.connector.Error as e:
            messagebox.showerror("Database error", str(e))
            return
        v["amount"].set("")
        v["desc"].set("")
        messagebox.showinfo("Saved", f"{ttype} saved.")
        self.refresh_all()


    def build_transactions(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="Transactions")

        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Label(bar, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.search_var, width=30)
        entry.pack(side="left", padx=5)
        entry.bind("<KeyRelease>", lambda e: self.refresh_transactions())
        ttk.Button(bar, text="Clear",
                   command=lambda: (self.search_var.set(""), self.refresh_transactions())).pack(side="left")

        self.tree = make_tree(f, height=15)
        self.tree.pack(fill="both", expand=True, pady=8)

        btns = ttk.Frame(f)
        btns.pack(fill="x")
        ttk.Button(btns, text="Edit Selected", command=self.edit_selected).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Delete Selected", command=self.delete_selected).pack(side="left")

    def refresh_transactions(self):
        fill_tree_tagged(self.tree, self.db.search(self.search_var.get().strip()))

    def selected_row(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select a transaction first.")
            return None
        return self.tree.item(sel[0])["values"]

    def delete_selected(self):
        row = self.selected_row()
        if row and messagebox.askyesno("Confirm", "Delete this transaction?"):
            self.db.delete(int(row[0]))
            self.refresh_all()

    def edit_selected(self):
        row = self.selected_row()
        if not row:
            return
        tid, ttype, d, cat, amt, desc = row
        tid, ttype, d, cat, amt, desc = int(tid), str(ttype), str(d), str(cat), str(amt), str(desc)

        win = tk.Toplevel(self)
        win.title(f"Edit {ttype}")
        win.grab_set()
        pad = ttk.Frame(win, padding=15)
        pad.pack()

        d_var, c_var = tk.StringVar(value=d), tk.StringVar(value=cat)
        a_var, n_var = tk.StringVar(value=amt), tk.StringVar(value=desc)

        ttk.Label(pad, text="Date").grid(row=0, column=0, sticky="w", pady=4)
        make_date_widget(pad, d_var).grid(row=0, column=1, sticky="w")

        ttk.Label(pad, text="Category").grid(row=1, column=0, sticky="w", pady=4)
        values = ["Income"] if ttype == "Income" else self.db.categories()
        ttk.Combobox(pad, textvariable=c_var, values=values, state="readonly",
                     width=20).grid(row=1, column=1, sticky="w")

        ttk.Label(pad, text="Amount (₹)").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(pad, textvariable=a_var, width=22).grid(row=2, column=1, sticky="w")

        ttk.Label(pad, text="Description").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(pad, textvariable=n_var, width=35).grid(row=3, column=1, sticky="w")

        def save():
            parsed = validate(d_var.get(), a_var.get())
            if not parsed:
                return
            self.db.update(tid, parsed[0], c_var.get(), parsed[1], n_var.get().strip())
            win.destroy()
            self.refresh_all()

        ttk.Button(pad, text="Save Changes", command=save).grid(row=4, column=1, sticky="w", pady=10)


    def refresh_all(self):
        cats = self.db.categories()
        self.expense_form["combo"]["values"] = cats
        if not self.expense_form["vars"]["category"].get() and cats:
            self.expense_form["vars"]["category"].set(cats[0])
        self.refresh_dashboard()
        self.refresh_transactions()


def fill_tree_tagged(tree, rows):
    tree.delete(*tree.get_children())
    for tid, ttype, d, cat, amt, desc in rows:
        tree.insert("", "end", tags=(ttype,),
                    values=(tid, ttype, d, cat, f"{float(amt):.2f}", desc or ""))


if __name__ == "__main__":
    try:
        database = Database()
    except mysql.connector.Error as err:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Connection failed", f"Could not connect to MySQL:\n{err}")
        raise SystemExit(1)
    App(database).mainloop()
