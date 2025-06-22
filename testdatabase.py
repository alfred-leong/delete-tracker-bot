from sqlalchemy import create_engine, text

# Replace with your actual connection string
# DB_URL = "postgresql://postgres:bt*+Bmun_.s5U-t@mztsazbtadyfrraqdkfn.supabase.co:5432/postgres"
DB_URL = "postgresql://postgres.mztsazbtadyfrraqdkfn:bt*+Bmun_.s5U-t@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"

engine = create_engine(DB_URL)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("✅ Connection successful! Result:", result.scalar())
except Exception as e:
    print("❌ Connection failed!")
    print(e)
