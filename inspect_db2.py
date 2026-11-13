import sqlite3, json, os

p = r"C:\Users\admin\Desktop\新建文件夹 (2)\紫鸟ebay\ecommerce-domestic.db"
con = sqlite3.connect(p)
cur = con.cursor()
for t in ["data_source_meta", "source_schema_record", "domestic_internal_data",
          "domestic_external_data", "domestic_collection_coverage",
          "domestic_metric_router_registry", "__ecomctl_init_state"]:
    n = cur.execute(f"select count(*) from '{t}'").fetchone()[0]
    cols = [c[1] for c in cur.execute(f"pragma table_info('{t}')")]
    print(f"-- {t} rows={n} cols={cols}")
    for row in cur.execute(f"select * from '{t}' limit 8"):
        s = str(row)
        print("   ", s[:400])
con.close()
