/**
 * 环境配置。
 * 注意：微信小程序运行时没有 Node 的 process 全局对象，
 * 不能写 process.env.*（会报 "process is not defined"）。
 * 这里使用编译期常量或硬编码。本地开发默认连 http://127.0.0.1:8000。
 */
const BASE_URL = 'http://127.0.0.1:8000'

export const API_BASE_URL = `${BASE_URL}/api`

/** 是否使用 mock 数据（后端未就绪时可开；接真实后端时改为 false） */
export const USE_MOCK = false
