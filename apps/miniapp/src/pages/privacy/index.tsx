/**
 * 隐私政策（用户系统合规落地页）
 */
import { Text, View } from '@tarojs/components'
import NavBar from '../../components/NavBar'
import './index.scss'

const SECTIONS = [
  {
    t: '一、我们收集的信息',
    p: '为提供核心服务，我们会收集：① 微信授权登录产生的账号标识（openid）；② 你主动填写的昵称与头像；③ 你主动设置的忌口、辣度、咸淡、技能水平等口味偏好；④ 你产生的问答历史、生成的菜谱与收藏记录；⑤ 为防滥用统计的 AI 调用次数。',
  },
  {
    t: '二、信息的使用',
    p: '上述信息用于：向你展示个性化菜谱推荐（口味偏好会注入 AI 生成过程）、保存你的问答与收藏以便随时回看、以及控制单日 AI 调用以保障服务质量与成本。',
  },
  {
    t: '三、信息的存储与保护',
    p: '你的数据存储于境内服务器（PostgreSQL 数据库），我们采取访问控制与加密传输等合理措施保护数据安全。AI 调用过程可能将你的问题与食材内容发送至大模型服务方用于生成结果，我们会在传输中做必要脱敏。',
  },
  {
    t: '四、信息共享',
    p: '我们不会向任何第三方出售你的个人信息。除法律要求或为提供所必需的服务方（如大模型服务商）外，不对外共享你的个人数据。',
  },
  {
    t: '五、你的权利',
    p: '你可以随时在「我的」中查看收藏与问答历史并单独删除，可清空全部历史；可修改昵称、头像与口味偏好；可在「注销账号」永久删除你的全部数据，注销后数据不可恢复。',
  },
  {
    t: '六、未成年人保护',
    p: '本服务面向一般烹饪爱好者。若你为未成年人，请在监护人指导下使用本服务。',
  },
  {
    t: '七、联系我们',
    p: '如对本隐私政策有任何疑问或意见，欢迎通过微信小程序内「免责声明与帮助」入口或官方渠道联系我们，我们将在合理期限内回复。',
  },
]

export default function Privacy() {
  return (
    <View className='page-content legal'>
      <NavBar title='隐私政策' showBack />
      <View className='legal-intro'>
        <Text>我们深知个人信息对你的重要性，将按法律法规要求保护你的隐私。</Text>
      </View>
      {SECTIONS.map((s) => (
        <View key={s.t} className='legal-card'>
          <Text className='legal-h'>{s.t}</Text>
          <Text className='legal-p'>{s.p}</Text>
        </View>
      ))}
      <View className='legal-footer'>
        <Text className='legal-date'>更新日期：2026-08-09</Text>
      </View>
    </View>
  )
}
