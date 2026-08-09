/// <reference types="@tarojs/taro" />

declare module '*.png'
declare module '*.gif'
declare module '*.jpg'
declare module '*.jpeg'
declare module '*.svg'
declare module '*.css'
declare module '*.less'
declare module '*.scss'
declare module '*.sass'
declare module '*.styl'

// Taro 配置宏（编译器注入全局）
declare function defineAppConfig(config: any): any
declare function definePageConfig(config: any): any
declare function defineComponentConfig(config: any): any

declare namespace NodeJS {
  interface ProcessEnv {
    /** 当前编译平台 */
    TARO_ENV: 'weapp' | 'h5' | 'rn' | 'swan' | 'alipay' | 'tt' | 'qq' | 'jd' | 'quickapp'
    /** 后端 API 地址（.env 中 TARO_APP_ 前缀注入） */
    TARO_APP_API_BASE_URL: string
  }
}
