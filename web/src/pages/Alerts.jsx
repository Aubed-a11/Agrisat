import { useState } from 'react'
import { BellRing } from 'lucide-react'
import { api, CROPS, isoDate, dateLabel, getSession } from '../api'
import { useMeta } from '../main'
import { PageHeader, Section, Notice, ErrorBox, Loading, Status, useLoad } from '../components/ui'

const LANGS = { fr: 'Français', bariba: 'Bariba', dendi: 'Dendi', ditammari: 'Ditammari', fon: 'Fon' }

export default function Alerts() {
  const meta = useMeta()
  const box = useLoad(() => api.get('/sms'), [])
  const [crop, setCrop] = useState('coton')
  const [doy, setDoy] = useState(236)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const isInsurer = ['assureur', 'admin'].includes(getSession().user.role)
  if (!meta) return <Loading />
  const run = async () => {
    setErr(null)
    try { const r = await api.post('/alerts/run', { crop, asof: isoDate(meta.campaign, doy) }); setMsg(`${r.sent} alertes de vigilance envoyées.`); box.reload() } catch (x) { setErr(x.message) }
  }
  return (
    <div>
      <PageHeader title="Alertes aux producteurs" description="Le producteur est prévenu par SMS quand l'indice de sa commune approche du seuil, puis à chaque déclenchement et paiement. Les versions en langues nationales ne partent qu'une fois traduites et validées par des locuteurs natifs." />
      {isInsurer && (
        <Section title="Lancer les alertes de vigilance" className="mb-4">
          <div className="flex flex-wrap items-end gap-3">
            <label><span className="label">Culture</span><select className="input w-32" value={crop} onChange={(e) => setCrop(e.target.value)}>{Object.entries(CROPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label className="flex-1 min-w-[240px]"><span className="label">Date d'analyse : {dateLabel(meta.campaign, doy)} {meta.campaign}</span>
              <input type="range" min={150} max={320} value={doy} onChange={(e) => setDoy(+e.target.value)} className="w-full accent-navy-700" /></label>
            <button className="btn-primary" onClick={run}><BellRing size={16} /> Envoyer</button>
          </div>
          <div className="mt-3 space-y-2"><ErrorBox error={err} /><Notice onClose={() => setMsg(null)}>{msg}</Notice></div>
        </Section>)}
      <Section title="Messages envoyés">
        {!box.data ? <Loading /> : box.data.length === 0 ? <p className="text-sm text-ink/60">Aucun message.</p> : (
          <div className="overflow-x-auto max-h-[600px]">
            <table className="w-full">
              <thead className="sticky top-0 bg-white"><tr><th className="th">Date</th><th className="th">Téléphone</th><th className="th">Langue</th><th className="th">Type</th><th className="th">Message</th><th className="th">Passerelle</th><th className="th">État</th></tr></thead>
              <tbody>{box.data.map((m) => (
                <tr key={m.id}><td className="td text-xs whitespace-nowrap">{new Date(m.created_at).toLocaleString('fr-FR')}</td><td className="td tabular-nums">{m.phone}</td>
                  <td className="td">{LANGS[m.language]}</td><td className="td">{m.category}</td><td className="td text-sm max-w-xl">{m.body}</td><td className="td text-xs">{m.provider}</td><td className="td"><Status value={m.status} /></td></tr>))}</tbody>
            </table>
          </div>)}
      </Section>
    </div>
  )
}
