import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'PANDA documentation',
  tagline: 'PERSEUS AI for Natural-language Data Analysis',
  favicon: 'img/canopy-leaf.svg',
  future: {v4: true},
  url: 'https://winterblacksmith.github.io',
  baseUrl: '/PANDA/',
  organizationName: 'winterblacksmith',
  projectName: 'PANDA',
  onBrokenLinks: 'throw',
  i18n: {defaultLocale: 'en', locales: ['en']},
  presets: [[
    'classic',
    {
      docs: {
        sidebarPath: './sidebars.ts',
        editUrl: 'https://github.com/winterblacksmith/PANDA/edit/docs/panda-handoff-starter/docs-site/',
        routeBasePath: 'docs',
      },
      blog: false,
      theme: {customCss: './src/css/custom.css'},
    } satisfies Preset.Options,
  ]],
  themeConfig: {
    image: 'img/age-species-2022.jpg',
    colorMode: {defaultMode: 'light', disableSwitch: false, respectPrefersColorScheme: true},
    navbar: {
      title: 'PANDA',
      logo: {alt: 'PANDA forestry AI', src: 'img/canopy-leaf.svg'},
      items: [
        {type: 'docSidebar', sidebarId: 'pandaSidebar', position: 'left', label: 'Documentation'},
        {to: '/docs/architecture/system-overview', label: 'Architecture', position: 'left'},
        {to: '/docs/handoff/project-handoff', label: 'Handoff', position: 'left'},
        {href: 'https://github.com/winterblacksmith/PANDA', label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'light',
      links: [
        {title: 'Documentation', items: [
          {label: 'PANDA overview', to: '/docs/overview'},
          {label: 'System architecture', to: '/docs/architecture/system-overview'},
          {label: 'Testing and troubleshooting', to: '/docs/operations/testing-troubleshooting'},
        ]},
        {title: 'Deployment', items: [
          {label: 'Irene inference service', to: '/docs/deployment/irene-ollama-fastapi'},
          {label: 'Railway application', to: '/docs/deployment/railway'},
          {label: 'GitHub repository', href: 'https://github.com/winterblacksmith/PANDA'},
        ]},
      ],
      copyright: `PANDA · PERSEUS AI for Natural-language Data Analysis · ${new Date().getFullYear()}`,
    },
    prism: {theme: prismThemes.github, darkTheme: prismThemes.dracula},
  } satisfies Preset.ThemeConfig,
};

export default config;