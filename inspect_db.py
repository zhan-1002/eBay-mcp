import sqlite3, sys

paths = [
    r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\ecommerce-domestic.db",
    r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\ecommerce-overseas.db",
]
for p in paths:
    print("=" * 20, p)
    con = sqlite3.connect(p)
    cur = con.cursor()
    tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
    print("tables:", tables)
    for t in tables:
        if any(k in t.lower() for k in ("store", "shop", "account", "bind")):
            try:
                cols = [c[1] for c in cur.execute(f"pragma table_info('{t}')")]
                n = cur.execute(f"select count(*) from '{t}'").fetchone()[0]
                print(f"-- {t} rows={n} cols={cols}")
                for row in cur.execute(f"select * from '{t}' limit 10"):
                    print("   ", row)
            except Exception as e:
                print("   err", e)
    con.close()
