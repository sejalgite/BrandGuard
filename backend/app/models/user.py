import enum
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Enum, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    CONTENT_CREATOR = "CONTENT_CREATOR"
    EXTERNAL_AGENCY = "EXTERNAL_AGENCY"
    REVIEWER = "REVIEWER"
    BRAND_MANAGER = "BRAND_MANAGER"
    LEGAL_REVIEWER = "LEGAL_REVIEWER"
    LEADERSHIP = "LEADERSHIP"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole, name="user_role"), nullable=False, default=UserRole.CONTENT_CREATOR)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_users_org_id"),
        UniqueConstraint("organization_id", "email", name="uq_org_email"),
    )

    organization = relationship("Organization", back_populates="users")

