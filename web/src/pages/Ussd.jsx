import { useState } from 'react'
import { Phone, RotateCcw } from 'lucide-react'
import { api } from '../api'
import { PageHeader, Section, useLoad } from '../components/ui'

export default function Ussd() {
  const farmers = useLoad(() => api.get('/farmers').catch(() => []), [])
  const [phone, setPhone] = useState('')
  const [path, setPath] = useState([])
  const [screen, setScreen] = useState('Composez *789# pour ouvrir le service AGRISAT.')
  const [input, setInput] = useState('')
  const [open, setOpen] = useState(false)

  const send = async (steps) => {
    const fd = new FormData()
    fd.append('sessionId', 'web'); fd.append('serviceCode', '*789#'); fd.append('phoneNumber', phone); fd.append('text', steps.join('*'))
    const r = await api.post('/ussd', fd)
    setScreen(r.replace(/^(CON|END) /, '')); setOpen(r.startsWith('CON')); setPath(steps); setInput('')
  }
  return (
    <div>
      <PageHeader title="Simulateur USSD" description="Le producteur consulte sa police, l'état de la pluie dans sa commune et ses indemnités depuis n'importe quel téléphone, sans internet. Le point d'accès est compatible avec les agrégateurs USSD." />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <Section title="Choisir un producteur de test">
          <select className="input" value={phone} onChange={(e) => { setPhone(e.target.value); setPath([]); setScreen('Composez *789# pour ouvrir le service AGRISAT.') }}>
            <option value="">Choisir</option>{(farmers.data || []).map((f) => <option key={f.id} value={f.phone}>{f.full_name}, {f.commune}, {f.phone}</option>)}
          </select>
          <p className="text-xs text-ink/60 mt-3">Point d'accès : POST /api/ussd avec sessionId, serviceCode, phoneNumber et text.</p>
        </Section>
        <div className="mx-auto w-72 rounded-[2rem] border-8 border-ink bg-ink p-3 shadow-lg">
          <div className="rounded-lg bg-[#e3f2fb] h-72 p-3 font-mono text-[13px] leading-snug whitespace-pre-wrap text-ink overflow-y-auto">{screen}</div>
          <div className="mt-3 flex gap-2">
            <input className="flex-1 rounded bg-white px-2 py-1.5 text-sm" value={input} disabled={!phone || (!open && path.length > 0)} onChange={(e) => setInput(e.target.value)} placeholder={open ? 'Votre choix' : ''} onKeyDown={(e) => e.key === 'Enter' && open && send([...path, input])} />
            {(!open || path.length === 0) && path.length === 0
              ? <button className="btn-primary !px-3" disabled={!phone} onClick={() => send([])}><Phone size={15} /></button>
              : open ? <button className="btn-primary !px-3" onClick={() => send([...path, input])}>OK</button>
                : <button className="btn-ghost !px-3" onClick={() => { setPath([]); setOpen(false); setScreen('Composez *789# pour ouvrir le service AGRISAT.') }}><RotateCcw size={15} /></button>}
          </div>
        </div>
      </div>
    </div>
  )
}
