/**
 * 用户协议（用户系统合规落地页）
 */
import { Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import NavBar from '../../components/NavBar'
import './index.scss'

const SECTIONS = [
  {
    t: '一、服务说明',
    p: 'ChefPal（厨伴）是一款口袋厨师微信小程序，提供问答学厨艺、食材推荐菜谱、收藏管理等功能。使用本服务即表示你同意本协议全部条款。',
  },
  {
    t: '二、账号与登录',
    p: '本服务通过微信授权登录建立账号。你应妥善保管微信账号及登录态，因保管不善造成的损失由你自行承担。你可在「我的-注销账号」永久删除账号及关联数据。',
  },
  {
    t: '三、生成内容免责',
    p: '菜谱与问答内容由小伴结合大模型生成，仅供烹饪参考，不构成医疗、营养或健康处方。涉及过敏原、疾病、孕期等特殊场景，请咨询专业医生或营养师。实际烹饪请以食材新鲜度与安全为准。',
  },
  {
    t: '四、用户行为规范',
    p: '你承诺不利用本服务从事违反法律法规、侵犯他人权益、发布违法违规内容等行为。你上传的头像、昵称等信息应合法合规，微信侧与平台将进行内容安全检测。',
  },
  {
    t: '五、账号注销',
    p: '你可在「我的-注销账号」发起注销。注销后，你的收藏、问答历史、生成的菜谱及调用记录将被永久删除且无法恢复。注销操作不可撤销，请谨慎操作。',
  },
  {
    t: '六、协议变更',
    p: '我们可能适时修订本协议，修订后将在本页面公示。若你继续使用本服务，即视为接受修订后的协议。',
  },
]

export default function Agreement() {
  return (
    <View className='page-content legal'>
      <NavBar title='用户协议' showBack />
      <View className='legal-intro'>
        <Text>欢迎使用 ChefPal！请仔细阅读以下用户协议。</Text>
      </View>
      {SECTIONS.map((s) => (
        <View key={s.t} className='legal-card'>
          <Text className='legal-h'>{s.t}</Text>
          <Text className='legal-p'>{s.p}</Text>
        </View>
      ))}
      <View className='legal-footer'>
        <Text className='legal-link' onClick={() => Taro.navigateTo({ url: '/pages/privacy/index' })}>
          查看《隐私政策》›
        </Text>
        <Text className='legal-date'>更新日期：2026-08-09</Text>
      </View>
    </View>
  )
}
