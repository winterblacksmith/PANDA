import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import styles from './index.module.css';

const flow = [
  ['01', 'Ask', 'A natural-language forestry question'],
  ['02', 'Calculate', 'Parameterized SQLite and spatial operations'],
  ['03', 'Verify', 'Tables, totals, charts, maps, and query proof'],
  ['04', 'Explain', 'Qwen turns verified results into clear language'],
  ['05', 'Remember', 'Conversation history persists in SQLite'],
];

export default function Home(): ReactNode {
  return (
    <Layout title="PANDA documentation" description="PERSEUS AI for Natural-language Data Analysis">
      <main>
        <section className={styles.hero}>
          <div className={`container ${styles.heroGrid}`}>
            <div>
              <p className={styles.kicker}>PERSEUS AI for Natural-language Data Analysis</p>
              <Heading as="h1">PANDA documentation</Heading>
              <p className={styles.lede}>
                Learn how PANDA combines forestry datasets, reproducible SQL, spatial analysis,
                persistent conversations, and a locally hosted language model.
              </p>
              <div className={styles.actions}>
                <Link className="button button--primary button--lg" to="/docs/overview">Start here</Link>
                <Link className={styles.textLink} to="/docs/handoff/project-handoff">Open the handoff guide →</Link>
              </div>
            </div>
            <figure className={styles.heroFigure}>
              <img src="img/tcuft-2022.jpg" alt="Cubic-foot volume per acre forestry map" />
              <figcaption>Example PANDA spatial output · cubic-foot volume per acre</figcaption>
            </figure>
          </div>
        </section>
        <section className={styles.flowSection}>
          <div className="container">
            <Heading as="h2">How PANDA works</Heading>
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
            <Heading as="h2">Project guides</Heading>
            <div className={styles.guideGrid}>
              <article><div className={styles.guideMark}>SYS</div><Heading as="h3">Architecture</Heading><p>See how the application, SQLite, spatial tools, FastAPI, Ollama, and Qwen fit together.</p><Link to="/docs/architecture/system-overview">Read the architecture →</Link></article>
              <article><div className={styles.guideMark}>GPU</div><Heading as="h3">Deployment</Heading><p>Operate the Irene inference service and connect it securely to the Railway application.</p><Link to="/docs/deployment/irene-ollama-fastapi">Read the deployment guide →</Link></article>
              <article><div className={styles.guideMark}>END</div><Heading as="h3">Handoff</Heading><p>Use the final checklist to transfer ownership, validate the system, and plan the next phase.</p><Link to="/docs/handoff/project-handoff">Read the handoff guide →</Link></article>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}