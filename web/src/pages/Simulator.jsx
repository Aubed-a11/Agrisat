import { useEffect, useState } from 'react'
import { ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts'
import { api, CROPS, fmt, pct } from '../api'
import { useMeta } from '../main'
import { PageHeader, Section, Field, Stat, ErrorBox, Notice, Loading } from '../components/ui'

export default function Simulator() {
  const meta = useMeta()
  const [f, setF] = useState({ commune_id: 1, crop: 'mais', product: 'rendement_zone', coverage: 0.8, area_ha: 2, live: false, n_sims: 10000 })
  const [real, setReal] = useState(null)
  useEffect(() => { api.get('/real-data').then(setReal).catch(() => {}) }, [])
  const [q, setQ] = useState(null)
  const [hist, setHist] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async (params = f) => {
    setBusy(true); setErr(null)
    try {
      const body = { ...params, product: params.crop === 'mais' ? params.product : 'indice_pluie' }
      const [r, h] = await Promise.all([api.post('/pricing/quote', body), api.get(`/contracts/${params.commune_id}/${params.crop}`)])
      setQ(r); setHist(h)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  useEffect(() => {
    run()
  }, []) // eslint-disable-line
  if (!meta) return <Loading />
  const rc = real?.communes?.find((c) => c.commune_id === f.commune_id)
  const chartRZ = q?.product === 'rendement_zone' && rc ? rc.series.filter((r) => !r.flag).map((r) => ({ year: r.year,
    indemnite: Math.max(0, q.coverage * r.trend - r.yield) / (q.coverage * r.trend) * (q.sum_insured),
    perte: r.loss_rel * r.trend * meta.crops.mais.price * f.area_ha })) : null
  const chart = chartRZ || hist?.history?.map((r) => ({ year: r.year, indemnite: r.payout_fcfa_ha * f.area_ha,
    perte: r.loss_rel != null ? r.loss_rel * (r.trend_kg_ha * meta.crops[f.crop].price) * f.area_ha : null }))

  return (
    <div>
      <PageHeader title="Simulateur de prime" description="Réponse immédiate à la question du producteur sur le terrain : combien je paie, combien je suis couvert, dans quels cas je suis payé." />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
        <Section title="Paramètres">
          <div className="space-y-3">
            <Field label="Commune"><select className="input" value={f.commune_id} onChange={(e) => setF({ ...f, commune_id: +e.target.value })}>
              {meta.communes.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.department})</option>)}</select></Field>
            <Field label="Culture"><select className="input" value={f.crop} onChange={(e) => setF({ ...f, crop: e.target.value })}>
              {Object.entries(CROPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            {f.crop === 'mais' && <Field label="Produit"><select className="input" value={f.product} onChange={(e) => setF({ ...f, product: e.target.value })}>
              <option value="rendement_zone">Rendement par zone (statistiques DSA)</option><option value="indice_pluie">Indice pluie satellitaire</option></select></Field>}
            {f.crop === 'mais' && f.product === 'rendement_zone' && <Field label="Seuil de couverture"><select className="input" value={f.coverage} onChange={(e) => setF({ ...f, coverage: +e.target.value })}>
              <option value={0.7}>70 % de la tendance</option><option value={0.8}>80 % de la tendance</option><option value={0.9}>90 % de la tendance</option></select></Field>}
            <Field label="Superficie (hectares)"><input className="input" type="number" min="0.25" step="0.25" value={f.area_ha} onChange={(e) => setF({ ...f, area_ha: +e.target.value })} /></Field>
            {!(f.crop === 'mais' && f.product === 'rendement_zone') && <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={f.live} onChange={(e) => setF({ ...f, live: e.target.checked })} />
              <span>Recalculer en direct par Monte Carlo<span className="block text-xs text-ink/55">Sinon, grille tarifaire de la campagne.</span></span></label>}
            {f.live && <Field label="Nombre de saisons simulées"><input className="input" type="number" min="500" max="50000" step="500" value={f.n_sims} onChange={(e) => setF({ ...f, n_sims: +e.target.value })} /></Field>}
            <button className="btn-primary w-full justify-center" onClick={() => run()} disabled={busy}>{busy ? 'Calcul en cours' : 'Calculer la prime'}</button>
            <ErrorBox error={err} />
          </div>
        </Section>
        <div className="lg:col-span-2 space-y-4">
          {q && <>
            {!q.insurable && <Notice tone="alert">{q.validated === false
              ? <>Indice pluie non validé : {q.basis_risk.correlation == null ? 'aucun rendement communal réel ne permet de le vérifier.' : `sa corrélation avec les pertes réelles est de ${fmt(q.basis_risk.correlation, 2)}, sous le minimum de 0,30.`} Il n'est pas commercialisé.{q.area_yield_available ? ' Pour le maïs, le contrat rendement par zone est disponible.' : ''}</>
              : <>Contrat non commercialisable dans cette commune : {pct(q.basis_risk.false_negative_rate, 0)} des années de forte perte n'auraient pas été indemnisées (seuil maximal 20 %).</>}</Notice>}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="Somme assurée" value={`${fmt(q.sum_insured)} F`} sub={`${fmt(q.sum_insured / q.area_ha)} FCFA par ha`} />
              <Stat label="Part producteur" value={`${fmt(q.premium_farmer)} F`} sub={`après subvention de ${pct(q.subsidy_rate, 0)}`} tone="ochre" />
              <Stat label="Prime commerciale" value={`${fmt(q.premium_total)} F`} sub={`taux ${pct(q.commercial_rate, 1)}`} />
              <Stat label="Probabilité d'indemnité" value={pct(q.prob_payout, 0)} sub={`${q.live_simulation ? 'simulation directe' : 'grille'}, ${fmt(q.n_sims)} saisons`} />
            </div>
            {q.product === 'rendement_zone' ? (
              <Section title="Quand l'assurance paie-t-elle ?">
                <p className="text-sm text-ink/80">L'indemnité est versée quand le rendement officiel du maïs dans la commune, publié par la DSA, passe sous {pct(q.coverage, 0)} de sa tendance, soit environ {fmt(q.coverage * q.trend_next)} kg/ha pour la prochaine campagne (tendance {fmt(q.trend_next)} kg/ha). Elle est proportionnelle à l'écart et versée par mobile money après publication des statistiques de campagne.</p>
                <p className="text-sm text-ink/60 mt-2">Sur {q.n_years} campagnes observées, ce contrat aurait payé {q.years_paid_historical} fois.</p>
              </Section>
            ) : (
            <Section title="Quand l'assurance paie-t-elle ?">
              <div className="overflow-x-auto"><table className="w-full">
                <thead><tr><th className="th">Phase</th><th className="th num">Part de la somme assurée</th><th className="th num">Déclenchement si pluie inférieure à</th><th className="th num">Indemnité totale si pluie inférieure à</th></tr></thead>
                <tbody>{q.phase_names.map((n, i) => (
                  <tr key={n} className={q.weights[i] === 0 ? 'text-ink/40' : ''}><td className="td whitespace-nowrap">{i + 1}. {n}</td><td className="td num">{pct(q.weights[i], 0)}</td>
                    <td className="td num">{q.weights[i] ? `${fmt(q.trigger[i])} mm` : 'non couverte'}</td><td className="td num">{q.weights[i] ? `${fmt(q.exit[i])} mm` : ''}</td></tr>))}</tbody>
              </table></div>
              <p className="text-sm text-ink/70 mt-3">Entre les deux seuils, l'indemnité augmente en proportion du manque de pluie. Elle est calculée sur la pluie satellitaire de la commune, sans visite de terrain, puis versée par mobile money. Si un crédit intrants est lié, il est remboursé en premier.</p>
            </Section>)}
            {chart && (
              <Section title={q.product === 'rendement_zone' ? 'Ce que le contrat aurait payé, rendements DSA réels' : 'Ce que le contrat aurait payé depuis 1981'} actions={q.basis_risk.correlation != null && <span className="text-xs text-ink/60">Corrélation avec les pertes {fmt(q.basis_risk.correlation, 2)}</span>}>
                <div style={{ height: 260 }}>
                  <ResponsiveContainer>
                    <ComposedChart data={chart}>
                      <CartesianGrid stroke="#eee" vertical={false} />
                      <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={3} />
                      <YAxis tick={{ fontSize: 11 }} width={70} tickFormatter={(v) => fmt(v)} />
                      <Tooltip formatter={(v) => `${fmt(v)} FCFA`} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="indemnite" name="Indemnité du contrat" fill="#1d4e89" />
                      <Line dataKey="perte" name="Perte de récolte estimée" stroke="#b42318" dot={{ r: 2 }} strokeWidth={1.5} connectNulls={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <p className="text-xs text-ink/55 mt-2">{q.product === 'rendement_zone' ? 'Rendements de maïs publiés par la DSA, 1995 à 2023, valeurs aberrantes écartées.' : 'Pertes disponibles sur les années avec rendement communal observé.'}</p>
              </Section>
            )}
          </>}
        </div>
      </div>
    </div>
  )
}
