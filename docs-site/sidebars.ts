import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  pandaSidebar: [
    {type: 'doc', id: 'overview', label: 'PANDA overview'},
    {type: 'doc', id: 'implementation-walkthrough', label: 'Implementation walkthrough'},
    {type: 'category', label: 'Getting started', items: ['getting-started/local-setup']},
    {type: 'category', label: 'Architecture', items: [
      'architecture/system-overview',
      'architecture/sql-chat',
    ]},
    {type: 'category', label: 'Data', items: ['data/fvs-treemap']},
    {type: 'category', label: 'Deployment', items: [
      'deployment/irene-ollama-fastapi',
      'deployment/railway',
    ]},
    {type: 'category', label: 'Operations', items: ['operations/testing-troubleshooting']},
    {type: 'category', label: 'Handoff', items: ['handoff/project-handoff']},
  ],
};

export default sidebars;