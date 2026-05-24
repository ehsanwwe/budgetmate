from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.goal import Goal
from app.schemas.goal import GoalCreate, GoalUpdate, GoalContribute, GoalOut

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=List[GoalOut])
def list_goals(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Goal).filter(Goal.user_id == current_user.id).all()


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(
    body: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = Goal(
        user_id=current_user.id,
        title=body.title,
        target_amount=body.target_amount,
        current_amount=body.current_amount or 0,
        deadline=body.deadline,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == current_user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="هدف یافت نشد")
    return goal


@router.put("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: int,
    body: GoalUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == current_user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="هدف یافت نشد")
    if body.title is not None:
        goal.title = body.title
    if body.target_amount is not None:
        goal.target_amount = body.target_amount
    if body.deadline is not None:
        goal.deadline = body.deadline
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == current_user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="هدف یافت نشد")
    db.delete(goal)
    db.commit()


@router.post("/{goal_id}/contribute", response_model=GoalOut)
def contribute_to_goal(
    goal_id: int,
    body: GoalContribute,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == current_user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="هدف یافت نشد")
    goal.current_amount = min(goal.current_amount + body.amount, goal.target_amount)
    db.commit()
    db.refresh(goal)
    return goal
