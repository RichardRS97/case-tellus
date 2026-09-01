import sqlite3, json
c = sqlite3.connect('tellus_financeiro.db')
for typ, name, sql in c.execute("select type,name,sql from sqlite_master"):
    print(typ, name)
    print(sql)
    print('---')
tables = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
for t in tables:
    n = c.execute(f'select count(*) from "{t}"').fetchone()[0]
    cols = [r[1] for r in c.execute(f'PRAGMA table_info("{t}")')]
    print(f'== {t} rows={n} cols={cols}')
    for row in c.execute(f'select * from "{t}" limit 5'):
        print('   ', row)
