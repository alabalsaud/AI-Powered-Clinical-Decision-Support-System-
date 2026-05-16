"""
Run this anytime to see all registered users in the database.
Command: python check_users.py
"""
from app.db.database import SessionLocal
from app.models.models import User

db = SessionLocal()
users = db.query(User).order_by(User.created_at.desc()).all()

print("\n" + "=" * 70)
print(f"   CDSS DATABASE — Total Users: {len(users)}")
print("=" * 70)

for u in users:
    status = "🔒 LOCKED" if u.account_locked else ("✅ Active" if u.is_active else "❌ Inactive")
    print(f"""
  ID       : {u.id}
  Name     : {u.full_name}
  Username : {u.username}
  Email    : {u.email}
  Role     : {u.role.value}
  Status   : {status}
  Joined   : {str(u.created_at)[:19]}
  Last Login: {str(u.last_login)[:19] if u.last_login else 'Never'}
  {'-' * 50}""")

db.close()
print("\n✅ Database check complete!\n")
