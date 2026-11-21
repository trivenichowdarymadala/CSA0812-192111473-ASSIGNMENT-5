"""Small reproducible benchmark: Python loop, pandas, and SQLite aggregation."""
import csv, random, sqlite3, time, statistics, argparse

def generate(path, n, seed=7):
    random.seed(seed)
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["station_id","pm25"])
        for i in range(n): w.writerow([f"ST{i%12+1:02d}", round(random.uniform(2,180),2)])

def loop_mean(path):
    sums={}; counts={}
    with open(path,encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v=float(row["pm25"]); k=row["station_id"]
            sums[k]=sums.get(k,0)+v; counts[k]=counts.get(k,0)+1
    return {k:sums[k]/counts[k] for k in sums}

def pandas_mean(path):
    import pandas as pd
    return pd.read_csv(path).groupby("station_id").pm25.mean().to_dict()

def sql_mean(path):
    con=sqlite3.connect(":memory:")
    con.execute("CREATE TABLE readings(station_id TEXT, pm25 REAL)")
    with open(path,encoding="utf-8") as f:
        con.executemany("INSERT INTO readings VALUES (?,?)",
                        ((r["station_id"],float(r["pm25"])) for r in csv.DictReader(f)))
    result=dict(con.execute("SELECT station_id, AVG(pm25) FROM readings GROUP BY station_id"))
    con.close(); return result

def run(path, repeats=3):
    funcs=[("Python loop",loop_mean),("pandas",pandas_mean),("SQLite",sql_mean)]
    results={}
    for name,fn in funcs:
        times=[]
        for _ in range(repeats):
            t=time.perf_counter(); out=fn(path); times.append(time.perf_counter()-t)
        results[name]={"median_seconds":round(statistics.median(times),6),"groups":len(out)}
    return results

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--rows",type=int,default=10000); ap.add_argument("--repeats",type=int,default=3); ap.add_argument("--csv",default="benchmark.csv"); a=ap.parse_args()
    generate(a.csv,a.rows); print(run(a.csv,a.repeats))
