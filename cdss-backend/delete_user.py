"""
Delete a registered user from the CDSS database.
Command: python delete_user.py
"""
from app.db.database import SessionLocal
from app.models.models import User

db = SessionLocal()

# Display all registered users
users = db.query(User).order_by(User.id).all()
print("\n" + "=" * 65)
print("   CDSS DATABASE — Registered Users")
print("=" * 65)
for u in users:
    print(f"  ID: {u.id:<4} |  Username: {u.username:<20} |  Email: {u.email}")

print("\n" + "-" * 65)

# Prompt for deletion
try:
    user_id = int(input("\n  Enter the ID of the user you want to delete: "))
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        print(f"\n  ❌ No user found with ID {user_id}.")
    else:
        confirm = input(
            f"\n  ⚠️  Are you sure you want to delete '{user.username}' ({user.email})? (yes/no): "
        )
        if confirm.strip().lower() == "yes":
            db.delete(user)
            db.commit()
            print(f"\n  ✅ User '{user.username}' has been successfully deleted.\n")
        else:
            print("\n  ❌ Deletion cancelled. No changes were made.\n")

except ValueError:
    print("\n  ❌ Invalid input. Please enter a numeric ID (e.g. 5).\n")

finally:
    db.close()
