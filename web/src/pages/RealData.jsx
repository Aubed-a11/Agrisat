import { useMemo, useState } from 'react'
import { ResponsiveContainer, ComposedChart, LineChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell } from 'recharts'
import { api, fmt, pct } from '../api'
import { PageHeader, Section, Stat, Loading, ErrorBox, useLoad } from '../components/ui'

const STATUS = {
  recupere: ['Récupéré, intégré', 'bg-sky-100 text-navy-700 border-sky-300'],
  a_telecharger: ['Script prêt, à lancer', 'bg-mist-100 text-ink/70 border-mist-200'],
  manquant: ['Aucune source ouverte', 'bg-ochre-500/10 text-ochre-600 border-ochre-500/30'],
}

export default function RealData() {
  const { data, error } = useLoad(() => api.get('/real-data'), [])
  const [cid, setCid] = useState(1)
  const [cov, setCov] = useState('0.8')
  const c = useMemo(() => data?.communes.find((x) => x.commune_id === cid), [data, cid])
  if (error) return <ErrorBox error={error} />
  if (!data) return <Loading />

  return (
    <div>
      <PageHeader title="Données réelles"
        description="Sources ouvertes repérées et intégrées : rendements communaux du maïs publiés par la DSA, FAOSTAT, prix de marché et limites officielles des communes. Le contrat d'assurance rendement par zone ci dessous est tarifé directement sur ces rendements observés." />

      {data.findings && (
        <Section title="Ce que disent les données réelles" className="mb-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div><div className="font-semibold mb-1">Pluie satellitaire</div><p className="text-ink/75">La pluie NASA POWER seule ne suit CHIRPS qu'à {fmt(data.findings.rain_validation?.season_corr_nasa_chirps_mean, 2)} de corrélation sur la saison. La pluie journalière est donc recalée sur les cumuls CHIRPS par décade (écart maximal {fmt(data.findings.rain_validation?.dekad_max_abs_error_after_recalibration_mm, 1)} mm). Données CHIRPS jusqu'au {data.findings.rain_validation?.chirps_last_dekad}.</p></div>
            <div><div className="font-semibold mb-1">Maïs</div><p className="text-ink/75">Sur 27 communes et 29 campagnes, l'indice pluie atteint en moyenne {fmt(data.findings.crops.mais.mean_correlation, 2)} de corrélation avec les pertes réelles, et {data.findings.crops.mais.n_validated} commune sur 27 passe le seuil de 0,30. Le produit retenu pour le maïs est le contrat rendement par zone.</p></div>
            <div><div className="font-semibold mb-1">Coton</div><p className="text-ink/75">Aucun rendement communal ouvert. Au niveau national (FAOSTAT, {data.findings.cotton_national_check?.n_years} ans), l'indice pluie moyen ne suit les pertes qu'à {fmt(data.findings.cotton_national_check?.correlation, 2)}. Les pires années, {data.findings.cotton_national_check?.worst_years_faostat?.join(', ')}, relèvent surtout de chocs de filière. L'indice coton reste non validé.</p></div>
          </div>
        </Section>
      )}

      <Section title="Catalogue des sources" className="mb-4">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr><th className="th">Donnée</th><th className="th">Plateforme</th><th className="th">Type</th><th className="th">Couverture</th><th className="th">Licence</th><th className="th">Usage dans AGRISAT</th><th className="th">État</th></tr></thead>
            <tbody>{data.sources.map((s) => {
              const [label, cls] = STATUS[s.status]
              return (
                <tr key={s.id}>
                  <td className="td font-semibold min-w-[220px]">{s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="hover:underline text-navy-700">{s.name}</a> : s.name}<div className="text-xs font-normal text-ink/55">{s.provider}</div></td>
                  <td className="td text-sm">{s.platform}</td><td className="td text-sm">{s.type}</td><td className="td text-sm">{s.coverage}</td>
                  <td className="td text-xs text-ink/65">{s.license}</td><td className="td text-sm">{s.use}</td>
                  <td className="td"><span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded border whitespace-nowrap ${cls}`}>{label}</span></td>
                </tr>)
            })}</tbody>
          </table>
        </div>
        <p className="text-xs text-ink/60 mt-3">Mise à jour : relancer <code className="bg-mist-100 px-1 rounded">python telecharger_donnees_agrisat.py</code>, puis <code className="bg-mist-100 px-1 rounded">python -m agrisat_core.sources.import_downloads agrisat_donnees.zip</code>. Les sources marquées « script prêt » se téléchargent sur votre machine avec <code className="bg-mist-100 px-1 rounded">python -m agrisat_core.sources.fetch_open_data all</code> (NASA POWER, HDX, FAOSTAT, Kaggle avec votre jeton), puis <code className="bg-mist-100 px-1 rounded">python -m agrisat_core.pipeline --source real</code>.</p>
      </Section>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label="Observations DSA, maïs" value={fmt(data.n_observations)} sub={`27 communes, ${data.years[0]} à ${data.years[1]}`} />
        <Stat label="Valeurs aberrantes écartées" value={data.n_flagged} sub="hors de 300 à 3 500 kg/ha ou écart extrême" tone="ochre" />
        <Stat label="Corrélation Nord et FAOSTAT" value={fmt(data.north_vs_faostat_corr, 2)} sub="rendement annuel moyen" />
        <Stat label="Prix producteur estimé du maïs" value={`${fmt(data.price.producer_price_estimate)} F/kg`} sub={`85 % du détail Natitingou et Parakou, ${fmt(data.price.retail_north_mean_2019_2024)} F`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <Section title="Rendement du maïs, 27 communes du Nord et Bénin (FAOSTAT)">
          <div style={{ height: 260 }}>
            <ResponsiveContainer><LineChart data={data.north_vs_faostat}>
              <CartesianGrid stroke="#e6edf3" vertical={false} /><XAxis dataKey="year" tick={{ fontSize: 11 }} interval={3} /><YAxis tick={{ fontSize: 11 }} width={48} domain={['auto', 'auto']} />
              <Tooltip formatter={(v) => `${fmt(v)} kg/ha`} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Line dataKey="north" name="Nord, DSA, moyenne pondérée" stroke="#0b2545" strokeWidth={2} dot={{ r: 2 }} />
              <Line dataKey="faostat" name="Bénin, FAOSTAT" stroke="#5fa8d3" strokeWidth={2} dot={{ r: 2 }} />
            </LineChart></ResponsiveContainer>
          </div>
        </Section>
        <Section title="Prix de détail du maïs (FCFA par kg)">
          <div style={{ height: 260 }}>
            <ResponsiveContainer><LineChart data={data.price.series}>
              <CartesianGrid stroke="#e6edf3" vertical={false} /><XAxis dataKey="date" tick={{ fontSize: 11 }} interval={7} /><YAxis tick={{ fontSize: 11 }} width={44} />
              <Tooltip formatter={(v) => `${fmt(v)} F`} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Line dataKey="cotonou" name="Cotonou" stroke="#9fb3c8" dot={false} connectNulls />
              <Line dataKey="parakou" name="Parakou" stroke="#0b2545" strokeWidth={2} dot={false} connectNulls />
              <Line dataKey="natitingou" name="Natitingou" stroke="#5fa8d3" strokeWidth={2} dot={false} connectNulls />
            </LineChart></ResponsiveContainer>
          </div>
        </Section>
      </div>

      <Section title="Rendements observés par commune" className="mb-4" actions={
        <select className="input w-56" value={cid} onChange={(e) => setCid(+e.target.value)}>{data.communes.map((x) => <option key={x.commune_id} value={x.commune_id}>{x.commune}</option>)}</select>}>
        {c && <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4 text-sm">
            <div><div className="text-xs text-ink/60">Rendement moyen</div><div className="font-semibold">{fmt(c.mean_yield)} kg/ha</div></div>
            <div><div className="text-xs text-ink/60">Tendance</div><div className="font-semibold">{c.trend_kg_ha_per_year > 0 ? '+' : ''}{fmt(c.trend_kg_ha_per_year, 1)} kg/ha par an</div></div>
            <div><div className="text-xs text-ink/60">Variabilité hors tendance</div><div className="font-semibold">{pct(c.cv_detrended)}</div></div>
            <div><div className="text-xs text-ink/60">Pires campagnes</div><div className="font-semibold">{c.worst_years.join(', ')}</div></div>
          </div>
          <div style={{ height: 280 }}>
            <ResponsiveContainer><ComposedChart data={c.series}>
              <CartesianGrid stroke="#e6edf3" vertical={false} /><XAxis dataKey="year" tick={{ fontSize: 11 }} interval={2} /><YAxis tick={{ fontSize: 11 }} width={48} />
              <Tooltip formatter={(v, n) => [`${fmt(v)} kg/ha`, n]} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="yield" name="Rendement DSA">{c.series.map((r, i) => <Cell key={i} fill={r.flag ? '#d9e3ed' : r.loss_rel > 0.3 ? '#b42318' : r.loss_rel > 0.15 ? '#c4841d' : '#5fa8d3'} />)}</Bar>
              <Line dataKey="trend" name="Tendance" stroke="#0b2545" strokeWidth={2} dot={false} />
            </ComposedChart></ResponsiveContainer>
          </div>
          <p className="text-xs text-ink/60 mt-2">En rouge, perte supérieure à 30 % de la tendance ; en orange, entre 15 et 30 % ; en gris clair, valeur écartée par le contrôle qualité.</p>
        </>}
      </Section>

      {c && (
        <Section title={`Contrat rendement par zone, maïs, ${c.commune}`} actions={
          <div className="flex gap-1">{data.params.coverage_levels.map((v) => (
            <button key={v} onClick={() => setCov(String(v))} className={`px-3 py-1.5 text-sm rounded-md border ${cov === String(v) ? 'bg-navy-700 text-white border-navy-700' : 'bg-white border-mist-200 hover:bg-mist-100'}`}>{pct(v, 0)}</button>))}
          </div>}>
          {(() => {
            const p = c.area_yield[cov]
            return (<>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                <Stat label="Prime pure" value={pct(p.pure_rate)} sub={`${fmt(p.pure_premium)} F par ha`} />
                <Stat label="Taux commercial" value={pct(p.commercial_rate)} sub={`diversification ${fmt(data.diversification[cov], 2)}`} />
                <Stat label="Part producteur par ha" value={`${fmt(p.farmer_premium)} F`} sub={`subvention ${pct(data.params.subsidy_rate, 0)}`} tone="ochre" />
                <Stat label="Campagnes indemnisées" value={`${p.years_paid_historical} sur ${c.series.length - c.n_flagged}`} sub={`probabilité simulée ${pct(p.prob_payout, 0)}`} />
              </div>
              <p className="text-sm text-ink/70">L'indemnité est versée quand le rendement officiel de la commune passe sous {pct(+cov, 0)} de sa tendance. Elle est proportionnelle à l'écart, pour une somme assurée de {fmt(data.params.sum_insured_ha)} FCFA par hectare. Ce produit, déjà utilisé pour le coton au Bénin, complète l'indice satellitaire : il ne dépend d'aucune donnée climatique, mais il paie plus tard, une fois les statistiques de campagne publiées.</p>
            </>)
          })()}
        </Section>
      )}
    </div>
  )
}
