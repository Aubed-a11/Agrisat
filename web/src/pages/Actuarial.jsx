import { useState } from 'react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Cell } from 'recharts'
import { api, CROPS, fmt, pct } from '../api'
import { PageHeader, Section, Stat, Loading, useLoad } from '../components/ui'

const M = (x) => `${fmt(x / 1e6, 0)} M`

export default function Actuarial() {
  const [crop, setCrop] = useState('coton')
  const contracts = useLoad(() => api.get(`/contracts?crop=${crop}`), [crop])
  const pf = useLoad(() => api.get('/portfolio'), [])
  if (!contracts.data || !pf.data) return <Loading />
  const p = pf.data
  const c = contracts.data
  const ok = c.filter((x) => x.insurable).length
  return (
    <div>
      <PageHeader title="Contrats et portefeuille"
        description="Paramètres optimisés par commune, primes par simulation Monte Carlo, risque de base mesuré sur l'historique, et risque agrégé de l'assureur avec réassurance en excédent de perte annuelle." />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label="Primes commerciales du portefeuille" value={`${M(p.premium_income)} F`} sub={`${fmt(p.total_insured_ha)} ha assurés`} />
        <Stat label="Ratio sinistres sur primes attendu" value={pct(p.expected_loss_ratio, 0)} sub={`probabilité de dépasser 100 % : ${pct(p.prob_loss_ratio_above_100, 1)}`} />
        <Stat label="CVaR 99,5 % des indemnités" value={`${M(p.cvar)} F`} sub={`VaR ${M(p.var)} F`} tone="alert" />
        <Stat label="Capital requis" value={`${M(p.capital_required)} F`} sub={`${M(p.stop_loss.capital_required_net)} F avec réassurance`} tone="ochre" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <Section title={`Distribution simulée du ratio sinistres sur primes (${fmt(p.n_sims)} saisons)`}>
          <div style={{ height: 240 }}>
            <ResponsiveContainer><BarChart data={p.histogram}>
              <CartesianGrid stroke="#eee" vertical={false} /><XAxis dataKey="bucket" tick={{ fontSize: 11 }} /><YAxis tickFormatter={(v) => pct(v, 0)} tick={{ fontSize: 11 }} width={56} />
              <Tooltip formatter={(v) => pct(v, 1)} />
              <Bar dataKey="share" name="Part des saisons">{p.histogram.map((h, i) => <Cell key={i} fill={i >= 4 ? '#b42318' : '#1d4e89'} />)}</Bar>
            </BarChart></ResponsiveContainer>
          </div>
          <p className="text-xs text-ink/60 mt-2">Facteur de diversification du capital entre communes : {fmt(p.diversification_factor, 2)}. Traité en excédent de perte de {pct(p.stop_loss.attachment_loss_ratio, 0)} à {pct(p.stop_loss.limit_loss_ratio, 0)} du ratio, coût estimé {M(p.stop_loss.reinsurance_premium)} FCFA.</p>
        </Section>
        <Section title="Rejeu historique sur le portefeuille actuel">
          <div style={{ height: 240 }}>
            <ResponsiveContainer><BarChart data={p.historical_replay}>
              <CartesianGrid stroke="#eee" vertical={false} /><XAxis dataKey="year" tick={{ fontSize: 11 }} interval={3} /><YAxis tickFormatter={(v) => pct(v, 0)} tick={{ fontSize: 11 }} width={56} />
              <Tooltip formatter={(v) => pct(v, 0)} /><ReferenceLine y={1} stroke="#b42318" strokeDasharray="4 3" />
              <Bar dataKey="loss_ratio" name="Ratio sinistres sur primes">{p.historical_replay.map((h, i) => <Cell key={i} fill={h.loss_ratio > 1 ? '#b42318' : '#9fb3c8'} />)}</Bar>
            </BarChart></ResponsiveContainer>
          </div>
          <p className="text-xs text-ink/60 mt-2">Pires années : {p.stress_worst_years.map((y) => `${y.year} (${pct(y.loss_ratio, 0)})`).join(', ')}.</p>
        </Section>
      </div>
      <Section title={`Contrats par commune, ${ok} sur ${c.length} commercialisables`} actions={
        <select className="input w-32" value={crop} onChange={(e) => setCrop(e.target.value)}>{Object.entries(CROPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr><th className="th">Commune</th><th className="th">Seuils phase 1 à 3 (mm)</th><th className="th">Sorties (mm)</th><th className="th num">Prime pure</th><th className="th num">Taux commercial</th><th className="th num">Part producteur par ha</th><th className="th num">Corrélation</th><th className="th num">Faux négatifs</th><th className="th num">Faux positifs</th><th className="th num">Gain d'équivalent certain</th><th className="th">Décision</th></tr></thead>
            <tbody>{c.map((x) => (
              <tr key={x.commune_id}>
                <td className="td font-semibold">{x.commune}</td>
                <td className="td tabular-nums text-xs">{x.trigger.slice(0, 3).map((v) => fmt(v)).join(', ')}</td>
                <td className="td tabular-nums text-xs">{x.exit.slice(0, 3).map((v) => fmt(v)).join(', ')}</td>
                <td className="td num">{pct(x.pricing.pure_rate)}</td><td className="td num">{pct(x.pricing.commercial_rate)}</td><td className="td num">{fmt(x.pricing.farmer_premium)} F</td>
                <td className="td num">{x.basis_risk.correlation == null ? '' : fmt(x.basis_risk.correlation, 2)}</td>
                <td className={`td num ${x.insurable ? '' : 'text-alert-600 font-semibold'}`}>{x.basis_risk.false_negative_rate == null ? 'aucune perte' : pct(x.basis_risk.false_negative_rate, 0)}</td>
                <td className="td num">{x.basis_risk.false_positive_rate == null ? '' : pct(x.basis_risk.false_positive_rate, 0)}</td>
                <td className="td num">{pct(x.ce_gain_pct)}</td>
                <td className="td text-xs">{x.insurable ? 'Commercialisable' : x.validated === false ? (x.basis_risk.correlation == null ? 'Non vérifiable' : 'Corrélation insuffisante') : 'Trop de pertes non payées'}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <p className="text-xs text-ink/60 mt-3">Un indice n'est proposé que si la corrélation entre ses indemnités et les pertes observées atteint 0,30. Règle du cahier des charges : un contrat dont plus de 20 % des années de forte perte n'auraient pas été indemnisées n'est pas proposé. Avec peu d'années de perte observées, cet indicateur reste fragile et doit être consolidé par les audits de terrain.</p>
      </Section>
    </div>
  )
}
