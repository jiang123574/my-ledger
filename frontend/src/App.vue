<script setup>
import { ref, onMounted, computed } from 'vue'

// --- 状态数据 ---
const activeTab = ref('record') 
const transactions = ref([])
const accounts = ref([])

// 表单数据
const form = ref({
  type: 'EXPENSE', 
  date: new Date().toISOString().split('T')[0], 
  amount: '',
  category: '',
  note: '',
  account_id: '',       
  target_account_id: '' 
})

// 账户表单增加初始余额
const accountForm = ref({ name: '', type: '现金', initial_balance: '' })

// --- API 交互 ---

const fetchData = async () => {
  try {
    const [accRes, transRes] = await Promise.all([
      fetch('/api/accounts'),
      fetch('/api/transactions')
    ])
    accounts.value = await accRes.json()
    transactions.value = await transRes.json()
    
    if (accounts.value.length > 0 && !form.value.account_id) {
      form.value.account_id = accounts.value[0].id
    }
  } catch (e) {
    console.error("加载数据失败", e)
  }
}

const submitTransaction = async () => {
  if (!form.value.amount || !form.value.account_id) {
    alert('请补全金额和账户信息')
    return
  }
  if (form.value.type === 'TRANSFER' && !form.value.target_account_id) {
    alert('请选择转入账户')
    return
  }

  const payload = {
    ...form.value,
    date: new Date(form.value.date).toISOString(),
    amount: Number(form.value.amount),
    account_id: Number(form.value.account_id),
    target_account_id: form.value.target_account_id ? Number(form.value.target_account_id) : null,
    category: form.value.type === 'TRANSFER' ? '转账' : form.value.category
  }

  try {
    const res = await fetch('/api/transactions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    
    if (!res.ok) {
      const data = await res.json()
      alert('保存失败: ' + JSON.stringify(data.detail))
      return
    }

    form.value.amount = ''
    form.value.note = ''
    if (form.value.type !== 'TRANSFER') form.value.category = ''
    await fetchData() 
  } catch (e) {
    alert('请求错误')
  }
}

const deleteTransaction = async (id) => {
  if (!confirm('确定删除？')) return
  await fetch(`/api/transactions/${id}`, { method: 'DELETE' })
  await fetchData()
}

const createAccount = async () => {
  if (!accountForm.value.name) return
  
  // 处理初始余额，如果没填默认为0
  const payload = {
    ...accountForm.value,
    initial_balance: accountForm.value.initial_balance ? Number(accountForm.value.initial_balance) : 0
  }

  await fetch('/api/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  
  accountForm.value.name = ''
  accountForm.value.initial_balance = ''
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

const getAmountStyle = (t) => {
  if (t.type === 'EXPENSE') return { color: '#e74c3c', text: `- ${t.amount}` }
  if (t.type === 'INCOME') return { color: '#27ae60', text: `+ ${t.amount}` }
  return { color: '#3498db', text: `${t.amount}` }
}

// 获取总资产
const totalAssets = computed(() => {
  return accounts.value.reduce((sum, acc) => sum + acc.balance, 0).toFixed(2)
})
</script>

<template>
  <div class="container">
    <h1 class="title">💰 个人财务中心</h1>

    <div class="tabs">
      <button :class="{ active: activeTab === 'record' }" @click="activeTab = 'record'">📝 记账</button>
      <button :class="{ active: activeTab === 'accounts' }" @click="activeTab = 'accounts'">💳 账户 & 余额</button>
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
              <option v-for="acc in accounts" :key="acc.id" :value="acc.id">
                {{ acc.name }} (¥{{ acc.balance }})
              </option>
            </select>
          </div>

          <div class="form-group" v-if="form.type === 'TRANSFER'">
            <label>转入账户</label>
            <select v-model="form.target_account_id">
              <option v-for="acc in accounts" :key="acc.id" :value="acc.id">
                {{ acc.name }} (¥{{ acc.balance }})
              </option>
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
                <span class="category" v-else>{{ t.account_name }} ➡ {{ t.target_account_name }}</span>
              </div>
              <div class="item-acc" v-if="t.type !== 'TRANSFER'">{{ t.account_name }}</div>
              <div class="item-note" v-if="t.note">{{ t.note }}</div>
            </div>
            <div class="item-right">
              <div class="amount" :style="{ color: getAmountStyle(t).color }">{{ getAmountStyle(t).text }}</div>
              <button class="btn-delete" @click="deleteTransaction(t.id)">×</button>
            </div>
          </li>
        </ul>
      </div>
    </div>

    <div v-if="activeTab === 'accounts'">
      
      <div class="card asset-card" style="background: linear-gradient(135deg, #3498db, #2980b9); color: white; margin-bottom: 20px;">
        <div style="font-size: 0.9em; opacity: 0.9;">总资产</div>
        <div style="font-size: 2.5em; font-weight: bold;">¥ {{ totalAssets }}</div>
      </div>

      <div class="card">
        <h3>新增账户</h3>
        <div class="form-grid" style="grid-template-columns: 2fr 1fr 1fr auto;">
          <input v-model="accountForm.name" placeholder="名称 (如: 招商银行)">
          <select v-model="accountForm.type">
            <option>现金</option>
            <option>储蓄卡</option>
            <option>信用卡</option>
            <option>支付宝/微信</option>
          </select>
          <input type="number" v-model="accountForm.initial_balance" placeholder="初始余额">
          <button class="btn-primary" @click="createAccount">添加</button>
        </div>
      </div>

      <div class="card" style="margin-top: 20px;">
        <h3>账户列表</h3>
        <ul style="padding: 0; list-style: none;">
          <li v-for="acc in accounts" :key="acc.id" class="account-item">
            <div class="acc-info">
              <strong>{{ acc.name }}</strong> 
              <span class="acc-type">{{ acc.type }}</span>
            </div>
            <div class="acc-balance" :class="{ negative: acc.balance < 0 }">
              ¥ {{ acc.balance }}
            </div>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style>
/* 复用之前的样式，并增加以下新样式 */
body { background-color: #f5f7fa; color: #333; }
.container { max-width: 600px; margin: 0 auto; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
.title { text-align: center; margin-bottom: 20px; }
.tabs { display: flex; margin-bottom: 20px; border-bottom: 2px solid #ddd; }
.tabs button { flex: 1; padding: 10px; border: none; background: none; cursor: pointer; font-size: 16px; color: #666; }
.tabs button.active { border-bottom: 2px solid #3498db; color: #3498db; font-weight: bold; margin-bottom: -2px; }
.card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
.type-toggle { display: flex; gap: 15px; margin-bottom: 15px; justify-content: center; }
.type-toggle label { cursor: pointer; display: flex; align-items: center; gap: 5px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
.form-group { display: flex; flex-direction: column; gap: 5px; }
.form-group label { font-size: 0.85em; color: #666; }
input, select { padding: 8px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; width: 100%; box-sizing: border-box; }
.full-width { width: 100%; box-sizing: border-box; }
.btn-primary { background: #3498db; color: white; border: none; padding: 10px; border-radius: 6px; cursor: pointer; font-size: 16px; }
.transaction-list { list-style: none; padding: 0; }
.list-item { background: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.item-left { display: flex; flex-direction: column; gap: 4px; }
.item-date { font-size: 0.8em; color: #999; }
.tag { font-size: 0.75em; padding: 2px 6px; border-radius: 4px; color: white; margin-right: 6px; }
.tag.EXPENSE { background: #e74c3c; }
.tag.INCOME { background: #27ae60; }
.tag.TRANSFER { background: #f39c12; }
.item-right { text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 5px; }
.amount { font-weight: bold; font-size: 1.1em; }
.btn-delete { background: none; border: none; color: #ccc; font-size: 1.2em; cursor: pointer; padding: 0 5px; }

/* 新增样式 */
.account-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #eee; }
.acc-type { background: #eee; color: #666; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-left: 8px; }
.acc-balance { font-weight: bold; font-size: 1.1em; color: #27ae60; }
.acc-balance.negative { color: #e74c3c; }
</style>