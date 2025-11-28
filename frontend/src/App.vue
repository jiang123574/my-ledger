<script setup>
import { ref, onMounted, computed } from 'vue'

// --- 状态数据 ---
const activeTab = ref('record') // 'record' (记账) 或 'accounts' (账户)
const transactions = ref([])
const accounts = ref([])

// 表单数据
const form = ref({
  type: 'EXPENSE', // EXPENSE, INCOME, TRANSFER
  date: new Date().toISOString().split('T')[0], // 默认为今天 YYYY-MM-DD
  amount: '',
  category: '',
  note: '',
  account_id: '',       // 主账户（支出方/收入方/转出方）
  target_account_id: '' // 目标账户（仅转账用）
})

const accountForm = ref({ name: '', type: '现金' }) // 新增账户表单

// --- API 交互 ---

// 1. 获取基础数据
const fetchData = async () => {
  const [accRes, transRes] = await Promise.all([
    fetch('/api/accounts'),
    fetch('/api/transactions')
  ])
  accounts.value = await accRes.json()
  transactions.value = await transRes.json()
  
  // 如果有账户且表单未选中，默认选中第一个
  if (accounts.value.length > 0 && !form.value.account_id) {
    form.value.account_id = accounts.value[0].id
  }
}

// 2. 提交记账
const submitTransaction = async () => {
  if (!form.value.amount || !form.value.account_id) {
    alert('请补全金额和账户信息')
    return
  }
  if (form.value.type === 'TRANSFER' && !form.value.target_account_id) {
    alert('请选择转入账户')
    return
  }

  // 构造提交数据
  const payload = {
    ...form.value,
    date: new Date(form.value.date).toISOString(), // 转换为 ISO 格式
    category: form.value.type === 'TRANSFER' ? '转账' : form.value.category
  }

  const res = await fetch('/api/transactions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })

  if (res.ok) {
    // 重置非固定字段
    form.value.amount = ''
    form.value.note = ''
    if (form.value.type !== 'TRANSFER') form.value.category = ''
    await fetchData() // 刷新
  } else {
    const err = await res.json()
    alert('保存失败: ' + err.detail)
  }
}

// 3. 删除交易
const deleteTransaction = async (id) => {
  if (!confirm('确定删除？')) return
  await fetch(`/api/transactions/${id}`, { method: 'DELETE' })
  await fetchData()
}

// 4. 新增账户
const createAccount = async () => {
  if (!accountForm.value.name) return
  await fetch('/api/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(accountForm.value)
  })
  accountForm.value.name = ''
  await fetchData()
}

// --- 辅助逻辑 ---
const transactionTypeLabel = (type) => {
  const map = { 'EXPENSE': '支出', 'INCOME': '收入', 'TRANSFER': '转账' }
  return map[type]
}

const formatTime = (isoString) => {
  return isoString.split('T')[0]
}

// 计算金额显示的颜色和符号
const getAmountStyle = (t) => {
  if (t.type === 'EXPENSE') return { color: '#e74c3c', text: `- ${t.amount}` }
  if (t.type === 'INCOME') return { color: '#27ae60', text: `+ ${t.amount}` }
  return { color: '#3498db', text: `${t.amount}` }
}

onMounted(fetchData)
</script>

<template>
  <div class="container">
    <h1 class="title">💰 个人财务中心</h1>

    <div class="tabs">
      <button :class="{ active: activeTab === 'record' }" @click="activeTab = 'record'">📝 记账</button>
      <button :class="{ active: activeTab === 'accounts' }" @click="activeTab = 'accounts'">💳 账户管理</button>
    </div>

    <div v-if="activeTab === 'record'">
      
      <div class="card form-card">
        <div class="type-toggle">
          <label><input type="radio" value="EXPENSE" v-model="form.type"> 支出</label>
          <label><input type="radio" value="INCOME" v-model="form.type"> 收入</label>
          <label><input type="radio" value="TRANSFER" v-model="form.type"> 转账</label>
        </div>

        <div class="form-grid">
          <div class="form-group">
            <label>日期</label>
            <input type="date" v-model="form.date">
          </div>
          
          <div class="form-group">
            <label>金额</label>
            <input type="number" v-model="form.amount" placeholder="0.00">
          </div>

          <div class="form-group">
            <label>{{ form.type === 'TRANSFER' ? '转出账户' : '账户' }}</label>
            <select v-model="form.account_id">
              <option v-for="acc in accounts" :key="acc.id" :value="acc.id">{{ acc.name }}</option>
            </select>
          </div>

          <div class="form-group" v-if="form.type === 'TRANSFER'">
            <label>转入账户</label>
            <select v-model="form.target_account_id">
              <option v-for="acc in accounts" :key="acc.id" :value="acc.id">{{ acc.name }}</option>
            </select>
          </div>

          <div class="form-group" v-if="form.type !== 'TRANSFER'">
            <label>分类</label>
            <input type="text" v-model="form.category" placeholder="如: 餐饮">
          </div>
        </div>

        <div class="form-group" style="margin-top: 10px;">
          <input type="text" v-model="form.note" placeholder="备注..." class="full-width">
        </div>

        <button class="btn-primary full-width" @click="submitTransaction" style="margin-top: 15px;">保存记录</button>
      </div>

      <div class="list-container">
        <h3>最近记录</h3>
        <ul class="transaction-list">
          <li v-for="t in transactions" :key="t.id" class="list-item">
            <div class="item-left">
              <div class="item-date">{{ formatTime(t.date) }}</div>
              <div class="item-main">
                <span class="tag" :class="t.type">{{ transactionTypeLabel(t.type) }}</span>
                <span class="category" v-if="t.type !== 'TRANSFER'">{{ t.category }}</span>
                <span class="category" v-else>
                  {{ t.account_name }} ➡ {{ t.target_account_name }}
                </span>
              </div>
              <div class="item-acc" v-if="t.type !== 'TRANSFER'">{{ t.account_name }}</div>
              <div class="item-note" v-if="t.note">{{ t.note }}</div>
            </div>
            
            <div class="item-right">
              <div class="amount" :style="{ color: getAmountStyle(t).color }">
                {{ getAmountStyle(t).text }}
              </div>
              <button class="btn-delete" @click="deleteTransaction(t.id)">×</button>
            </div>
          </li>
        </ul>
      </div>
    </div>

    <div v-if="activeTab === 'accounts'">
      <div class="card">
        <h3>新增账户</h3>
        <div style="display: flex; gap: 10px;">
          <input v-model="accountForm.name" placeholder="账户名称 (如: 招商银行)" style="flex: 2">
          <select v-model="accountForm.type" style="flex: 1">
            <option>现金</option>
            <option>储蓄卡</option>
            <option>信用卡</option>
            <option>支付宝/微信</option>
          </select>
          <button class="btn-primary" @click="createAccount">添加</button>
        </div>
      </div>

      <div class="card" style="margin-top: 20px;">
        <h3>账户列表</h3>
        <ul style="padding-left: 20px;">
          <li v-for="acc in accounts" :key="acc.id" style="margin-bottom: 8px;">
            <strong>{{ acc.name }}</strong> 
            <span style="color: #666; font-size: 0.9em; margin-left: 10px;">({{ acc.type }})</span>
          </li>
        </ul>
      </div>
    </div>

  </div>
</template>

<style>
/* 简单的样式优化 */
body { background-color: #f5f7fa; color: #333; }
.container { max-width: 600px; margin: 0 auto; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
.title { text-align: center; margin-bottom: 20px; }

/* Tabs */
.tabs { display: flex; margin-bottom: 20px; border-bottom: 2px solid #ddd; }
.tabs button { flex: 1; padding: 10px; border: none; background: none; cursor: pointer; font-size: 16px; color: #666; }
.tabs button.active { border-bottom: 2px solid #3498db; color: #3498db; font-weight: bold; margin-bottom: -2px; }

/* Cards */
.card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }

/* Form */
.type-toggle { display: flex; gap: 15px; margin-bottom: 15px; justify-content: center; }
.type-toggle label { cursor: pointer; display: flex; align-items: center; gap: 5px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
.form-group { display: flex; flex-direction: column; gap: 5px; }
.form-group label { font-size: 0.85em; color: #666; }
input, select { padding: 8px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
.full-width { width: 100%; box-sizing: border-box; }
.btn-primary { background: #3498db; color: white; border: none; padding: 10px; border-radius: 6px; cursor: pointer; font-size: 16px; transition: background 0.2s; }
.btn-primary:hover { background: #2980b9; }

/* List */
.transaction-list { list-style: none; padding: 0; }
.list-item { background: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.item-left { display: flex; flex-direction: column; gap: 4px; }
.item-date { font-size: 0.8em; color: #999; }
.tag { font-size: 0.75em; padding: 2px 6px; border-radius: 4px; color: white; margin-right: 6px; }
.tag.EXPENSE { background: #e74c3c; }
.tag.INCOME { background: #27ae60; }
.tag.TRANSFER { background: #f39c12; }
.item-acc { font-size: 0.8em; color: #666; }
.item-note { font-size: 0.8em; color: #999; font-style: italic; }
.item-right { text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 5px; }
.amount { font-weight: bold; font-size: 1.1em; }
.btn-delete { background: none; border: none; color: #ccc; font-size: 1.2em; cursor: pointer; padding: 0 5px; }
.btn-delete:hover { color: #e74c3c; }
</style>