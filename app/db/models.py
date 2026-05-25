from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    current_state: Mapped[str] = mapped_column(String(64), default="start", nullable=False)
    user_type: Mapped[str | None] = mapped_column(String(64))

    projects: Mapped[list["Project"]] = relationship(back_populates="user")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
    followup_events: Mapped[list["FollowupEvent"]] = relationship(back_populates="user")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_value: Mapped[str | None] = mapped_column(Text)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="new", nullable=False)

    user: Mapped["User"] = relationship(back_populates="projects")
    audience_profile: Mapped["AudienceProfile | None"] = relationship(back_populates="project")
    ideas: Mapped[list["Idea"]] = relationship(back_populates="project")
    posts: Mapped[list["Post"]] = relationship(back_populates="project")


class AudienceProfile(Base):
    __tablename__ = "audience_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True)
    niche: Mapped[str] = mapped_column(Text, nullable=False)
    audience_summary: Mapped[str] = mapped_column(Text, nullable=False)
    pains_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    desires_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    beliefs_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    tone_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_analysis_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="audience_profile")


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    angle: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="ideas")
    posts: Mapped[list["Post"]] = relationship(back_populates="idea")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    idea_id: Mapped[int | None] = mapped_column(ForeignKey("ideas.id", ondelete="SET NULL"), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    generation_type: Mapped[str] = mapped_column(String(64), default="free", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="posts")
    idea: Mapped["Idea | None"] = relationship(back_populates="posts")


class Tariff(Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    projects_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    posts_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_price: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    payments: Mapped[list["Payment"]] = relationship(back_populates="tariff")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="tariff")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="pending", nullable=False)
    provider: Mapped[str] = mapped_column(String(64), default="mock", nullable=False)
    external_payment_id: Mapped[str | None] = mapped_column(String(255))
    payment_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="payments")
    tariff: Mapped["Tariff"] = relationship(back_populates="payments")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(64), default="active", nullable=False)
    projects_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    posts_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    posts_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    tariff: Mapped["Tariff"] = relationship(back_populates="subscriptions")


class FollowupEvent(Base):
    __tablename__ = "followup_events"
    __table_args__ = (UniqueConstraint("user_id", "event_type", name="uq_followup_user_event_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(64), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="followup_events")
