import sqlite3
from config import DB_PATH

print("DB_PATH=", DB_PATH)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("select id, contract_number, contract_type from contracts where contract_number=?", ("SOZ0007",))
print("contract=", cur.fetchone())

cur.execute("""
select count(*)
from route_params rp
join contracts c on c.id=rp.contract_id
where c.contract_number=?
""", ("SOZ0007",))
print("route_params_count=", cur.fetchone()[0])

cur.execute("""
select count(*), min(effective_from), max(effective_from)
from trip_prices tp
join contracts c on c.id=tp.contract_id
where c.contract_number=?
  and length(coalesce(tp.pricing_category,''))>0
""", ("SOZ0007",))
print("tariff_rows=", cur.fetchone())

cur.execute("""
select tp.route_params_id, tp.service_type, tp.pricing_category, tp.effective_from, tp.price, tp.subcontractor_price
from trip_prices tp
join contracts c on c.id=tp.contract_id
where c.contract_number=?
  and length(coalesce(tp.pricing_category,''))>0
order by tp.effective_from desc, tp.route_params_id
limit 50
""", ("SOZ0007",))
rows = cur.fetchall()
print("sample_rows=")
for r in rows:
    print(r)

conn.close()
