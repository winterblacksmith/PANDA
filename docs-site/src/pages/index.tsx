import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import styles from './index.module.css';

const flow = [
  ['01', 'Question', 'Natural-language forestry question'],
  ['02', 'Local Qwen', 'Intent and concise explanation'],
  ['03', 'SQLite', 'Parameterized, reproducible query'],
  ['04', 'Spatial data', 'CSV, FVS, shapefile and TreeMap'],
  ['05', 'Evidence', 'Tables, charts and maps'],
];

export default function Home(): ReactNode {
  return (
    <Layout title="Canopy documentation" description="Local-first forestry AI knowledge base documentation">
      <main>
        <section className={styles.hero}>
          <div className={`container ${styles.heroGrid}`}>
            <div>
              <p className={styles.kicker}>Forestry AI knowledge base</p>
              <Heading as="h1">Canopy documentation</Heading>
              <p className={styles.lede}>
                Understand how Canopy queries forestry tables, FVS stand results, shapefiles,
                and TreeMap rasters—locally, with inspectable SQL and saved chat history.
              </p>
              <div className={styles.actions}>
                <Link className="button button--primary button--lg" to="/docs/overview">Start with Section 1</Link>
                <Link className={styles.textLink} to="/docs/data/fvs-treemap">Explore the data →</Link>
              </div>
            </div>
            <figure className={styles.heroFigure}>
              <img src="img/tcuft-2022.jpg" alt="Cubic foot volume per acre map supplied with the FVS results" />
              <figcaption>Example forestry output · cubic-foot volume per acre, 2022</figcaption>
            </figure>
          </div>
        </section>

        <section className={styles.flowSection}>
          <div className="container">
            <Heading as="h2">How Canopy works</Heading>
            <div className={styles.flow}>
              {flow.map(([number, title, detail]) => (
                <div className={styles.flowStep} key={number}>
                  <span>{number}</span><strong>{title}</strong><small>{detail}</small>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.guides}>
          <div className="container">
            <Heading as="h2">Explore the implementation</Heading>
            <div className={styles.guideGrid}>
              <article>
                <div className={styles.guideMark}>SQL</div>
                <Heading as="h3">SQL queries and saved chats</Heading>
                <p>See exactly how CSV data becomes a local SQLite table and how every query is bound safely.</p>
                <Link to="/docs/architecture/sql-chat">Read the architecture →</Link>
              </article>
              <article>
                <div className={styles.guideMark}>FVS</div>
                <Heading as="h3">FVS stand results</Heading>
                <p>Query 20,069 modeled stands, chart acres by age, and retrieve polygons through unique MU_ID values.</p>
                <Link to="/docs/data/fvs-treemap">Read the data guide →</Link>
              </article>
              <article>
                <div className={styles.guideMark}>TIF</div>
                <Heading as="h3">TreeMap raster</Heading>
                <p>Display actual raster cells and connect FVS selections to TreeMap Band 1 through TM_Value.</p>
                <Link to="/docs/data/fvs-treemap#the-two-spatial-joins">Understand the join →</Link>
              </article>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
