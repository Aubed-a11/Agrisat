import { FileDown, Sheet } from 'lucide-react'
import { api, CROPS, download, fmt, pct } from '../api'
import { useMeta } from '../main'
import { PageHeader, Section, Stat, Loading, useLoad } from '../components/ui'

export default function Reports() {
  const meta = useMeta()
  const { data } = useLoad(() => meta ? api.get(`/reports/summary?campaign=${meta.campaign}`) : Promise.resolve(null), [meta?.campaign])
  if (!meta || !data) return <Loading />
  const t = data.totals
  return (
    <div>
      <PageHeader title={`Rapport de campagne ${data.campaign}`} description="Suivi de la couverture, de la subvention publique et des indemnités pour l'assureur, le FNDA, le MAEP et les bailleurs."
        actions={<>
          <button className="btn-ghost" onClick={() => download(`/reports/export.pdf?campaign=${data.campaign}`, `agrisat_${data.campaign}.pdf`)}><FileDown size={16} /> Export PDF</button>
          <button className="btn-ghost" onClick={() => download(`/reports/export.xlsx?campaign=${data.campaign}`, `agrisat_${data.campaign}.xlsx`)}><Sheet size={16} /> Export Excel</button>
        </>} />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Stat label="Producteurs assurés" value={fmt(t.farmers)} sub={`${fmt(t.policies)} polices, ${fmt(t.area_ha, 1)} ha`} />
        <Stat label="Somme assurée" value={`${fmt(t.sum_insured)} F`} />
        <Stat label="Subvention publique" value={`${fmt(t.premium_subsidy)} F`} sub={`sur ${fmt(t.premium_total)} F de primes`} tone="ochre" />
        <Stat label="Indemnités" value={`${fmt(t.payouts)} F`} sub={`ratio sinistres sur primes ${pct(t.loss_ratio, 0)}`} tone="alert" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label="Indemnités payées" value={`${fmt(t.payouts_paid)} F`} />
        <Stat label="Primes non encaissées" value={fmt(t.premium_unpaid)} />
        <Stat label="Réclamations" value={fmt(t.claims)} sub={`${fmt(t.claims_in_audit)} en audit`} />
        <Stat label="Paiements en échec" value={fmt(t.payments_failed)} />
      </div>
      <Section title="Détail par commune et culture">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>{['Commune', 'Département', 'Culture', 'Polices', 'Superficie', 'Somme assurée', 'Prime totale', 'Subvention', 'Part producteurs', 'Indemnités', 'S/P'].map((h, i) => <th key={h} className={`th ${i > 2 ? 'num' : ''}`}>{h}</th>)}</tr></thead>
            <tbody>{data.by_commune.map((r) => (
              <tr key={r.commune + r.crop}><td className="td font-semibold">{r.commune}</td><td className="td">{r.department}</td><td className="td">{CROPS[r.crop]}</td>
                <td className="td num">{r.policies}</td><td className="td num">{fmt(r.area_ha, 1)}</td><td className="td num">{fmt(r.sum_insured)}</td><td className="td num">{fmt(r.premium_total)}</td>
                <td className="td num">{fmt(r.premium_subsidy)}</td><td className="td num">{fmt(r.premium_farmer)}</td><td className="td num">{fmt(r.payouts)}</td>
                <td className={`td num ${r.loss_ratio > 1 ? 'text-alert-600 font-semibold' : ''}`}>{pct(r.loss_ratio, 0)}</td></tr>))}</tbody>
          </table>
        </div>
      </Section>
    </div>
  )
}
