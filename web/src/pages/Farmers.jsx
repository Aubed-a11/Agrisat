import { useState } from 'react'
import { UserPlus, Upload, Search } from 'lucide-react'
import { api } from '../api'
import { useMeta } from '../main'
import { PageHeader, Section, Field, ErrorBox, Notice, Loading, useLoad } from '../components/ui'

const LANGS = { fr: 'Français', bariba: 'Bariba', dendi: 'Dendi', ditammari: 'Ditammari', fon: 'Fon' }
const OPS = { mtn: 'MTN MoMo', moov: 'Moov Money', celtiis: 'Celtiis Cash' }
const EMPTY = { full_name: '', phone: '', operator: 'mtn', language: 'fr', commune_id: 1, village: '', consent: false }

export default function Farmers() {
  const meta = useMeta()
  const [q, setQ] = useState('')
  const list = useLoad(() => api.get(`/farmers${q ? `?q=${encodeURIComponent(q)}` : ''}`), [q])
  const [f, setF] = useState(EMPTY)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const [imp, setImp] = useState(null)

  const save = async (e) => {
    e.preventDefault(); setErr(null)
    try { const r = await api.post('/farmers', f); setMsg(`${r.full_name} enregistré.`); setF(EMPTY); list.reload() } catch (x) { setErr(x.message) }
  }
  const upload = async (e) => {
    const file = e.target.files[0]; if (!file) return
    const fd = new FormData(); fd.append('file', file)
    try { const r = await api.post('/farmers/import', fd); setImp(r); list.reload() } catch (x) { setErr(x.message) }
    e.target.value = ''
  }
  if (!meta) return <Loading />
  return (
    <div>
      <PageHeader title="Producteurs" description="Enregistrement individuel ou import groupé par la coopérative. Le consentement est obligatoire et daté. Le téléphone sert au paiement mobile money et aux alertes." />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
        <div className="space-y-4">
          <Section title="Nouveau producteur">
            <form onSubmit={save} className="space-y-3">
              <Field label="Nom complet"><input className="input" required value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
              <Field label="Téléphone" hint="10 chiffres commençant par 01"><input className="input" required value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="01 97 00 00 00" /></Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Opérateur"><select className="input" value={f.operator} onChange={(e) => setF({ ...f, operator: e.target.value })}>{Object.entries(OPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
                <Field label="Langue des alertes"><select className="input" value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })}>{Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              </div>
              <Field label="Commune"><select className="input" value={f.commune_id} onChange={(e) => setF({ ...f, commune_id: +e.target.value })}>{meta.communes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
              <Field label="Village"><input className="input" value={f.village} onChange={(e) => setF({ ...f, village: e.target.value })} /></Field>
              <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} />
                <span>Le producteur consent au traitement de ses données pour la gestion de son assurance.</span></label>
              <button className="btn-primary w-full justify-center"><UserPlus size={16} /> Enregistrer</button>
              <ErrorBox error={err} />
              <Notice onClose={() => setMsg(null)}>{msg}</Notice>
            </form>
          </Section>
          <Section title="Import groupé (CSV)">
            <p className="text-sm text-ink/70 mb-3">Colonnes attendues : nom, telephone, operateur, langue, commune, village, consentement (oui ou non).</p>
            <label className="btn-ghost cursor-pointer"><Upload size={16} /> Choisir un fichier<input type="file" accept=".csv" className="hidden" onChange={upload} /></label>
            {imp && <div className="mt-3 text-sm"><Notice>{imp.imported} producteurs importés, {imp.errors.length} lignes rejetées.</Notice>
              {imp.errors.length > 0 && <ul className="mt-2 text-xs text-alert-600 space-y-0.5">{imp.errors.slice(0, 10).map((e) => <li key={e.ligne}>Ligne {e.ligne} : {e.erreur}</li>)}</ul>}</div>}
          </Section>
        </div>
        <Section title={`Producteurs enregistrés (${list.data?.length ?? ''})`} className="lg:col-span-2"
          actions={<div className="relative"><Search size={14} className="absolute left-2.5 top-2.5 text-ink/40" /><input className="input pl-8 w-56" placeholder="Nom ou téléphone" value={q} onChange={(e) => setQ(e.target.value)} /></div>}>
          {list.loading && !list.data ? <Loading /> : (
            <div className="overflow-x-auto max-h-[640px]">
              <table className="w-full">
                <thead className="sticky top-0 bg-white"><tr><th className="th">Nom</th><th className="th">Téléphone</th><th className="th">Opérateur</th><th className="th">Langue</th><th className="th">Commune</th><th className="th">Coopérative</th></tr></thead>
                <tbody>{list.data?.map((r) => (
                  <tr key={r.id}><td className="td font-semibold">{r.full_name}</td><td className="td tabular-nums">{r.phone}</td><td className="td">{OPS[r.operator] || r.operator}</td>
                    <td className="td">{LANGS[r.language]}</td><td className="td">{r.commune}</td><td className="td text-ink/70">{r.cooperative || ''}</td></tr>))}</tbody>
              </table>
            </div>)}
        </Section>
      </div>
    </div>
  )
}
