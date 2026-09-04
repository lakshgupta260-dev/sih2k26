import sys
from app.db.session import SessionLocal
from app.models.user import User
from app.models.project import Project, ProjectMembership
from app.core.security import hash_password
from app.core.constants import UserRole

def seed_test_user(phone: str):
    db = SessionLocal()
    try:
        # Check if user exists
        user = db.query(User).filter(User.phone == phone).first()
        if not user:
            user = User(
                email=f"{phone}@test.com",
                hashed_password=hash_password("password123"),
                full_name="Test User",
                phone=phone,
                role=UserRole.SITE_SUPERVISOR
            )
            db.add(user)
            db.flush()
            print(f"Created User: {user.id}")
            
        # Create a test project
        project = db.execute(select(Project).where(Project.code == "TEST-01")).scalars().first()
        if not project:
            project = Project(
                name="Plan2Progress Demo Project",
                description="Testing WhatsApp and Vapi",
                code="TEST-01",
                created_by_id=user.id
            )
            db.add(project)
            db.flush()
            print(f"Created Project: {project.id}")
        else:
            print(f"Found Project: {project.id}")
        
        # Add membership
        membership = db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project.id,
                ProjectMembership.user_id == user.id
            )
        ).scalars().first()
        if not membership:
            membership = ProjectMembership(
                project_id=project.id,
                user_id=user.id,
                role=UserRole.PROJECT_MANAGER
            )
            db.add(membership)
        
        db.commit()
        print("Successfully seeded test user and project!")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    phone = sys.argv[1]
    seed_test_user(phone)
