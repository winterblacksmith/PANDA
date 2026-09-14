import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  canopySidebar: [
    {type: 'doc', id: 'overview', label: '1. Canopy overview'},
    {type: 'doc', id: 'implementation-walkthrough', label: '2. Implementation walkthrough'},
    {
      type: 'category',
      label: 'Getting started',
      items: ['getting-started/local-setup'],
    },
    {
      type: 'category',
      label: 'Data',
      items: ['data/fvs-treemap'],
    },
    {
      type: 'category',
      label: 'Architecture',
      items: ['architecture/sql-chat'],
    },
  ],
};

export default sidebars;
