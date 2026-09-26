<template>
  <section class="page" data-module="cranestat">
    <header class="page-head">
      <div>
        <h2>岸桥作业量统计</h2>
        <p class="page-desc">按设备编号与班次统计岸桥作业量、司机与作业区域；班次视图汇总各班次作业量与设备状态分布，数据实时取自岸桥设备清单。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" :disabled="loading" @click="loadAll">
          {{ loading ? '刷新中…' : '刷新数据' }}
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in summaryCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="{ 'stat-warn': item.warn }">{{ item.value }}</strong>
      </article>
    </div>

    <!-- 班次作业量视图 -->
    <section class="section-block">
      <div class="section-head">
        <h3>班次作业量视图</h3>
        <div v-if="shiftError" class="error-inline">
          <span>{{ shiftError }}</span>
          <button class="btn small" type="button" @click="loadShifts">重试</button>
        </div>
      </div>
      <table v-if="!shiftError" class="data-table">
        <thead>
          <tr>
            <th>班次</th>
            <th>作业量合计</th>
            <th>参与设备数</th>
            <th>台均作业量</th>
            <th>记录数</th>
            <th>设备状态分布（取自设备清单）</th>
            <th>异常情况</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in shifts" :key="item['班次']" :class="{ 'row-weak': item['效率偏低'] }">
            <td>
              {{ item['班次'] }}
              <span v-if="item['效率偏低']" class="tag tag-warn">效率偏低</span>
            </td>
            <td>{{ item['作业量合计'] }}</td>
            <td>{{ item['参与设备数'] }}</td>
            <td>{{ item['台均作业量'] }}</td>
            <td>{{ item['记录数'] }}</td>
            <td>
              <span v-for="dist in item['设备状态分布']" :key="dist['设备状态']" class="dist-item">
                <span :class="['status-dot', statusClass(dist['设备状态'])]"></span>
                {{ dist['设备状态'] }} {{ dist['数量'] }}
              </span>
            </td>
            <td>
              <span v-if="item['作业量空值数']" class="tag tag-warn">作业量为空 {{ item['作业量空值数'] }}</span>
              <span v-if="item['挂不上台账数']" class="tag tag-warn">挂不上设备 {{ item['挂不上台账数'] }}</span>
              <span v-if="!item['作业量空值数'] && !item['挂不上台账数']" class="text-muted">无</span>
            </td>
          </tr>
          <tr v-if="!shifts.length">
            <td colspan="7" class="empty-state">暂无班次作业量数据</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 异常记录 -->
    <section class="section-block">
      <div class="section-head">
        <h3>待核对异常记录</h3>
        <span class="text-muted">作业量为空、设备编号缺失或挂不上设备清单的记录单独列出</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>设备编号</th>
            <th>班次</th>
            <th>作业量</th>
            <th>司机姓名</th>
            <th>作业区域</th>
            <th>异常标记</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in abnormalRows" :key="String(row.id)" class="row-abnormal">
            <td>{{ row['设备编号'] || '—' }}</td>
            <td>{{ row['班次'] ?? '—' }}</td>
            <td>
              <span v-if="row['作业量为空']" class="tag tag-warn">未填报</span>
              <span v-else>{{ row['作业量'] }}</span>
            </td>
            <td>{{ row['司机姓名'] ?? '—' }}</td>
            <td>{{ row['作业区域'] ?? '—' }}</td>
            <td>
              <span v-for="flag in splitFlags(row['异常标记'])" :key="flag" class="tag tag-warn">{{ flag }}</span>
            </td>
          </tr>
          <tr v-if="!abnormalRows.length">
            <td colspan="6" class="empty-state">暂无异常记录，作业量与设备编号均已核对通过</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 作业明细 -->
    <section class="section-block">
      <div class="section-head">
        <h3>作业量明细</h3>
        <div v-if="recordsError" class="error-inline">
          <span>{{ recordsError }}</span>
          <button class="btn small" type="button" @click="loadRecords">重试</button>
        </div>
      </div>

      <form class="filter-bar" @submit.prevent="loadRecords">
        <label class="filter-item">
          <span>设备编号</span>
          <input v-model="filters.keyword" placeholder="按设备编号检索" />
        </label>
        <label class="filter-item">
          <span>班次</span>
          <select v-model="filters.shift">
            <option value="">全部班次</option>
            <option v-for="shift in shiftOptions" :key="shift" :value="shift">{{ shift }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>异常筛选</span>
          <select v-model="filters.abnormal">
            <option value="">全部记录</option>
            <option value="all">仅看异常记录</option>
            <option value="empty">作业量为空</option>
            <option value="unmatched">设备编号挂不上</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-abnormal': row['异常标记'] }">
            <td v-for="column in columns" :key="column">
              <template v-if="column === '作业量'">
                <span v-if="row['作业量为空']" class="tag tag-warn">未填报</span>
                <span v-else>{{ row[column] }}</span>
              </template>
              <template v-else-if="column === '台账设备状态'">
                <span v-if="row[column]" :class="['tag', statusClass(row[column])]">{{ row[column] }}</span>
                <span v-else class="tag tag-warn">台账无此设备</span>
              </template>
              <template v-else-if="column === '异常标记'">
                <span v-for="flag in splitFlags(row[column])" :key="flag" class="tag tag-warn">{{ flag }}</span>
                <span v-if="!row[column]" class="text-muted">正常</span>
              </template>
              <template v-else>{{ row[column] || '—' }}</template>
            </td>
          </tr>
          <tr v-if="!rows.length && !recordsError">
            <td :colspan="columns.length" class="empty-state">当前筛选条件下没有岸桥作业量记录</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ total }} 条作业量记录</span>
        <span class="text-muted">设备状态每次刷新都从岸桥设备清单实时获取，与台账保持一致</span>
      </footer>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type StatusCount = { 设备状态: string; 数量: number }
type ShiftStat = {
  班次: string
  记录数: number
  作业量合计: number
  参与设备数: number
  已匹配设备数: number
  台均作业量: number
  作业量空值数: number
  挂不上台账数: number
  设备状态分布: StatusCount[]
  挂不上设备编号: string[]
  效率偏低?: boolean
}
type ShiftView = {
  items: ShiftStat[]
  summary: {
    台账设备数: number
    流水记录数: number
    作业量合计: number
    作业量空值数: number
    挂不上台账记录数: number
    班次数: number
  }
}
type StatRow = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/crane-stat'
const columns = ['设备编号', '班次', '作业量', '司机姓名', '作业区域', '台账设备状态', '异常标记']
const shiftOptions = ['早班', '中班', '夜班']
const PAGE_SIZE = 200

const rows = ref<StatRow[]>([])
const total = ref(0)
const shifts = ref<ShiftStat[]>([])
const summary = ref<ShiftView['summary'] | null>(null)

const recordsError = ref('')
const shiftError = ref('')
const loading = ref(false)

const filters = reactive({ keyword: '', shift: '', abnormal: '' })

const abnormalRows = computed(() =>
  rows.value.filter((row) => Boolean(row['异常标记'])),
)

const summaryCards = computed(() => {
  const data = summary.value
  return [
    { label: '台账设备数', value: data ? data.台账设备数 : '—', warn: false },
    { label: '作业量合计', value: data ? data.作业量合计 : '—', warn: false },
    { label: '作业班次', value: data ? data.班次数 : '—', warn: false },
    { label: '作业量为空', value: data ? data.作业量空值数 : '—', warn: Boolean(data && data.作业量空值数 > 0) },
    { label: '挂不上台账', value: data ? data.挂不上台账记录数 : '—', warn: Boolean(data && data.挂不上台账记录数 > 0) },
  ]
})

function splitFlags(value: unknown): string[] {
  return typeof value === 'string' && value ? value.split('、') : []
}

function statusClass(status: unknown): string {
  switch (status) {
    case '作业中':
      return 'tag-green'
    case '待保养':
      return 'tag-amber'
    case '已停机':
      return 'tag-gray'
    default:
      return 'tag-blue'
  }
}

function resetFilters() {
  filters.keyword = ''
  filters.shift = ''
  filters.abnormal = ''
  void loadRecords()
}

async function loadRecords() {
  recordsError.value = ''
  const params = new URLSearchParams({ page: '1', size: String(PAGE_SIZE) })
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.shift) params.set('shift', filters.shift)
  if (filters.abnormal) params.set('abnormal', filters.abnormal)
  try {
    const response = await request(`${ENDPOINT}/records?${params.toString()}`)
    if (!response.ok) {
      throw new Error(`作业量明细取数失败（接口返回 ${response.status}），请重试`)
    }
    const payload = (await response.json()) as { items?: StatRow[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    recordsError.value = error instanceof Error ? error.message : '作业量明细取数失败，请重试'
  }
}

async function loadShifts() {
  shiftError.value = ''
  try {
    const response = await request(`${ENDPOINT}/shifts`)
    if (!response.ok) {
      throw new Error(`班次作业量视图取数失败（接口返回 ${response.status}），请重试`)
    }
    const payload = (await response.json()) as ShiftView
    shifts.value = payload.items ?? []
    summary.value = payload.summary ?? null
  } catch (error) {
    shiftError.value = error instanceof Error ? error.message : '班次作业量视图取数失败，请重试'
  }
}

async function loadAll() {
  loading.value = true
  try {
    // 两份数据相互独立，分别取数、分别报错与重试
    await Promise.all([loadRecords(), loadShifts()])
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>
