import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Canopy documentation',
  tagline: 'Query forestry tables and spatial data locally.',
  favicon: 'img/canopy-leaf.svg',
  future: {v4: true},
  url: 'https://winterblacksmith.github.io',
  baseUrl: '/tree_ai_demo/',
  organizationName: 'winterblacksmith',
  projectName: 'tree_ai_demo',
  onBrokenLinks: 'throw',
  i18n: {defaultLocale: 'en', locales: ['en']},
  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/winterblacksmith/tree_ai_demo/edit/main/docs-site/',
          routeBasePath: 'docs',
        },
        blog: false,
        theme: {customCss: './src/css/custom.css'},
      } satisfies Preset.Options,
    ],
  ],
  themeConfig: {
    image: 'img/age-species-2022.jpg',
    colorMode: {defaultMode: 'light', disableSwitch: false, respectPrefersColorScheme: true},
    navbar: {
      title: 'Canopy',
      logo: {alt: 'Canopy leaf', src: 'img/canopy-leaf.svg'},
      items: [
        {type: 'docSidebar', sidebarId: 'canopySidebar', position: 'left', label: 'Docs'},
        {to: '/docs/data/fvs-treemap', label: 'Data', position: 'left'},
        {to: '/docs/architecture/sql-chat', label: 'Architecture', position: 'left'},
        {href: 'https://github.com/winterblacksmith/tree_ai_demo', label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'light',
      links: [
        {title: 'Documentation', items: [
          {label: 'Canopy overview', to: '/docs/overview'},
          {label: 'FVS and TreeMap', to: '/docs/data/fvs-treemap'},
          {label: 'SQL and chat persistence', to: '/docs/architecture/sql-chat'},
        ]},
        {title: 'Project', items: [
          {label: 'GitHub repository', href: 'https://github.com/winterblacksmith/tree_ai_demo'},
          {label: 'Run Canopy locally', to: '/docs/getting-started/local-setup'},
        ]},
      ],
      copyright: `Canopy forestry AI knowledge base · ${new Date().getFullYear()}`,
    },
    prism: {theme: prismThemes.github, darkTheme: prismThemes.dracula},
  } satisfies Preset.ThemeConfig,
};

export default config;
