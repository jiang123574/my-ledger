from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import os
from sqlalchemy import event

# 1. 数据库配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/test.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# 【针对 M4/Docker 优化】开启 SQLite WAL 模式
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)




# 2. 定义数据库模型 (Table)
class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float)
    category = Column(String)
    note = Column(String, nullable=True)
    date = Column(DateTime, default=datetime.now)

# 创建表
Base.metadata.create_all(bind=engine)

# 3. Pydantic 模型 (用于请求体验证)
class TransactionCreate(BaseModel):
    amount: float
    category: str
    note: str = None

class TransactionOut(TransactionCreate):
    id: int
    date: datetime
    class Config:
        orm_mode = True

# 4. FastAPI 实例
app = FastAPI()

# 依赖项：获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 5. API 路由
@app.get("/api/transactions", response_model=list[TransactionOut])
def read_transactions(db: Session = Depends(get_db)):
    return db.query(Transaction).all()

@app.post("/api/transactions", response_model=TransactionOut)
def create_transaction(item: TransactionCreate, db: Session = Depends(get_db)):
    db_item = Transaction(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


# 新增：删除交易的接口
@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    # 1. 在数据库中查找对应的记录
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    
    # 2. 如果找不到，返回 404 错误
    if transaction is None:
        raise HTTPException(status_code=404, detail="未找到该记录")
    
    # 3. 删除并提交更改
    db.delete(transaction)
    db.commit()
    
    return {"message": "删除成功"}