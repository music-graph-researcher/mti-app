# Validación empírica MTI (E3–E6)

`run_id`: `c6d66e354c5a4f2f`

`evidence_status`: `empirical_frozen`

## 1. Composición del corpus

| Ocurrencias | Familias | Grupos | Scopes | Consultas elegibles | Consultas excluidas |
|---:|---:|---:|---:|---:|---:|
| 121 | 26 | 5 | 11 | 121 | 0 |

## 2. Folds y parámetros seleccionados

| Fold | Test | Development mAP | Development MRR | Parámetros seleccionados |
|---:|---|---:|---:|---|
| 1 | bachBWV889Fg | 0.9074 | 0.9867 | `{'omega_pc': '1/2', 'omega_lin': '1/2', 'omega_on': '2', 'omega_off': '2', 'gamma': '6'}` |
| 2 | beethovenOp2No1Mvt3 | 0.8817 | 0.9857 | `{'omega_pc': '1/2', 'omega_lin': '1/2', 'omega_on': '1', 'omega_off': '1', 'gamma': '6'}` |
| 3 | chopinOp24No4 | 0.8926 | 0.9870 | `{'omega_pc': '1/2', 'omega_lin': '1/2', 'omega_on': '1', 'omega_off': '1', 'gamma': '6'}` |
| 4 | gibbonsSilverSwan1612 | 0.9598 | 1.0000 | `{'omega_pc': '1/2', 'omega_lin': '1/2', 'omega_on': '1', 'omega_off': '1', 'gamma': '6'}` |
| 5 | mozartK282Mvt2 | 0.8724 | 0.9825 | `{'omega_pc': '1/2', 'omega_lin': '1/2', 'omega_on': '1', 'omega_off': '1', 'gamma': '6'}` |

## 3. Recuperación principal (E4) — pooled

| mAP | MRR | Recall@1 | Recall@10 |
|---:|---:|---:|---:|
| 0.9017 | 0.9800 | 0.3195 | 0.8978 |

## 4. Recuperación principal (E4) — macro-fold

| mAP | MRR | Recall@1 | Recall@10 |
|---:|---:|---:|---:|
| 0.9074 | 0.9796 | 0.3282 | 0.9137 |

## 5. Ablaciones por fold (E3)

| Fold | Variante | mAP | ΔmAP | MRR | ΔMRR | R@1 | R@10 | estado métrico |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | estructura temporal + cardinalidad, sin altura | 0.9537 | 0.0789 | 0.9683 | 0.0159 | 0.1603 | 0.9810 | experimental_dissimilarity |
| 1 | altura cromática relativa completa | 0.8847 | 0.0100 | 0.9683 | 0.0159 | 0.1603 | 0.9673 | pseudometric_ablation |
| 1 | clase de altura relativa módulo 12 | 0.9144 | 0.0396 | 0.9444 | -0.0079 | 0.1508 | 0.9578 | pseudometric_ablation |
| 1 | altura + ataque | 0.8850 | 0.0102 | 1.0000 | 0.0476 | 0.1671 | 0.9689 | pseudometric_ablation |
| 1 | altura + ataque + terminación sin cardinalidad | 0.3097 | -0.5651 | 0.3872 | -0.5652 | 0.0340 | 0.2689 | experimental_dissimilarity |
| 1 | perfil MTI completo | 0.8748 | 0.0000 | 0.9524 | 0.0000 | 0.1481 | 0.9621 | metric_profile |
| 1 | perfil completo sin registro lineal | 0.9104 | 0.0356 | 0.9286 | -0.0238 | 0.1413 | 0.9673 | pseudometric_ablation |
| 1 | sensibilidad a gamma = 1 | 0.5397 | -0.3351 | 0.8206 | -0.1317 | 0.1159 | 0.5841 | metric_profile |
| 1 | sensibilidad a gamma = 2 | 0.7139 | -0.1609 | 0.9206 | -0.0317 | 0.1413 | 0.7834 | metric_profile |
| 1 | sensibilidad a gamma = 3 | 0.7912 | -0.0836 | 0.9206 | -0.0317 | 0.1413 | 0.8741 | metric_profile |
| 1 | sensibilidad a gamma = 4 | 0.8286 | -0.0462 | 0.9444 | -0.0079 | 0.1481 | 0.8946 | metric_profile |
| 1 | sensibilidad a gamma = 6 | 0.8748 | 0.0000 | 0.9524 | 0.0000 | 0.1481 | 0.9621 | metric_profile |
| 2 | estructura temporal + cardinalidad, sin altura | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | experimental_dissimilarity |
| 2 | altura cromática relativa completa | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | pseudometric_ablation |
| 2 | clase de altura relativa módulo 12 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | pseudometric_ablation |
| 2 | altura + ataque | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | pseudometric_ablation |
| 2 | altura + ataque + terminación sin cardinalidad | 0.9587 | -0.0413 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | experimental_dissimilarity |
| 2 | perfil MTI completo | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | metric_profile |
| 2 | perfil completo sin registro lineal | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | pseudometric_ablation |
| 2 | sensibilidad a gamma = 1 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | metric_profile |
| 2 | sensibilidad a gamma = 2 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | metric_profile |
| 2 | sensibilidad a gamma = 3 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | metric_profile |
| 2 | sensibilidad a gamma = 4 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | metric_profile |
| 2 | sensibilidad a gamma = 6 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.5242 | 1.0000 | metric_profile |
| 3 | estructura temporal + cardinalidad, sin altura | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | experimental_dissimilarity |
| 3 | altura cromática relativa completa | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | pseudometric_ablation |
| 3 | clase de altura relativa módulo 12 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | pseudometric_ablation |
| 3 | altura + ataque | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | pseudometric_ablation |
| 3 | altura + ataque + terminación sin cardinalidad | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | experimental_dissimilarity |
| 3 | perfil MTI completo | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | metric_profile |
| 3 | perfil completo sin registro lineal | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | pseudometric_ablation |
| 3 | sensibilidad a gamma = 1 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | metric_profile |
| 3 | sensibilidad a gamma = 2 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | metric_profile |
| 3 | sensibilidad a gamma = 3 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | metric_profile |
| 3 | sensibilidad a gamma = 4 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | metric_profile |
| 3 | sensibilidad a gamma = 6 | 1.0000 | 0.0000 | 1.0000 | 0.0000 | 0.4286 | 1.0000 | metric_profile |
| 4 | estructura temporal + cardinalidad, sin altura | 0.9676 | 0.2712 | 0.9712 | 0.0256 | 0.2055 | 0.9573 | experimental_dissimilarity |
| 4 | altura cromática relativa completa | 0.6752 | -0.0213 | 0.8301 | -0.1154 | 0.1628 | 0.6906 | pseudometric_ablation |
| 4 | clase de altura relativa módulo 12 | 0.7173 | 0.0209 | 0.8825 | -0.0630 | 0.1790 | 0.7407 | pseudometric_ablation |
| 4 | altura + ataque | 0.6907 | -0.0058 | 0.8974 | -0.0481 | 0.1824 | 0.6930 | pseudometric_ablation |
| 4 | altura + ataque + terminación sin cardinalidad | 0.3223 | -0.3742 | 0.6992 | -0.2463 | 0.0781 | 0.2845 | experimental_dissimilarity |
| 4 | perfil MTI completo | 0.6965 | 0.0000 | 0.9455 | 0.0000 | 0.1944 | 0.7017 | metric_profile |
| 4 | perfil completo sin registro lineal | 0.7237 | 0.0272 | 0.9455 | 0.0000 | 0.1944 | 0.7270 | pseudometric_ablation |
| 4 | sensibilidad a gamma = 1 | 0.5316 | -0.1648 | 0.9551 | 0.0096 | 0.1944 | 0.4614 | metric_profile |
| 4 | sensibilidad a gamma = 2 | 0.5349 | -0.1615 | 0.9455 | 0.0000 | 0.1944 | 0.4324 | metric_profile |
| 4 | sensibilidad a gamma = 3 | 0.5690 | -0.1275 | 0.9455 | 0.0000 | 0.1944 | 0.5778 | metric_profile |
| 4 | sensibilidad a gamma = 4 | 0.6295 | -0.0670 | 0.9455 | 0.0000 | 0.1944 | 0.6272 | metric_profile |
| 4 | sensibilidad a gamma = 6 | 0.6965 | 0.0000 | 0.9455 | 0.0000 | 0.1944 | 0.7017 | metric_profile |
| 5 | estructura temporal + cardinalidad, sin altura | 0.9657 | 0.0000 | 1.0000 | 0.0000 | 0.3456 | 0.9045 | experimental_dissimilarity |
| 5 | altura cromática relativa completa | 0.9657 | 0.0000 | 1.0000 | 0.0000 | 0.3456 | 0.9045 | pseudometric_ablation |
| 5 | clase de altura relativa módulo 12 | 0.9657 | 0.0000 | 1.0000 | 0.0000 | 0.3456 | 0.9045 | pseudometric_ablation |
| 5 | altura + ataque | 0.9657 | 0.0000 | 1.0000 | 0.0000 | 0.3456 | 0.9045 | pseudometric_ablation |
| 5 | altura + ataque + terminación sin cardinalidad | 0.9773 | 0.0116 | 1.0000 | 0.0000 | 0.3456 | 0.9727 | experimental_dissimilarity |
| 5 | perfil MTI completo | 0.9657 | 0.0000 | 1.0000 | 0.0000 | 0.3456 | 0.9045 | metric_profile |
| 5 | perfil completo sin registro lineal | 0.9657 | 0.0000 | 1.0000 | 0.0000 | 0.3456 | 0.9045 | pseudometric_ablation |
| 5 | sensibilidad a gamma = 1 | 1.0000 | 0.0343 | 1.0000 | 0.0000 | 0.3456 | 0.9727 | metric_profile |
| 5 | sensibilidad a gamma = 2 | 1.0000 | 0.0343 | 1.0000 | 0.0000 | 0.3456 | 0.9727 | metric_profile |
| 5 | sensibilidad a gamma = 3 | 0.9782 | 0.0125 | 1.0000 | 0.0000 | 0.3456 | 0.9318 | metric_profile |
| 5 | sensibilidad a gamma = 4 | 0.9657 | 0.0000 | 1.0000 | 0.0000 | 0.3456 | 0.9045 | metric_profile |
| 5 | sensibilidad a gamma = 6 | 0.9657 | 0.0000 | 1.0000 | 0.0000 | 0.3456 | 0.9045 | metric_profile |

## 6. Ablaciones globales pooled (E3)

Bootstrap: `paired_group_bootstrap` · unidad `provenance_group` · `replicates = 10000` · `seed = 2026` · `n_groups = 5` · percentiles `—`/`—`.

| Variante | pooled mAP | ΔmAP | IC 95% (ΔmAP) | pooled MRR | ΔMRR | pooled R@1 | pooled R@10 | estado métrico |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A0 | 0.9737 | 0.0720 | [0.0000, 0.1888] | 0.9883 | 0.0083 | 0.3240 | 0.9560 | experimental_dissimilarity |
| A1 | 0.8989 | -0.0028 | [-0.0131, 0.0054] | 0.9580 | -0.0220 | 0.3149 | 0.8963 | pseudometric_ablation |
| A2 | 0.9131 | 0.0114 | [0.0000, 0.0274] | 0.9651 | -0.0149 | 0.3167 | 0.9054 | pseudometric_ablation |
| A3 | 0.9022 | 0.0005 | [-0.0035, 0.0056] | 0.9780 | -0.0021 | 0.3203 | 0.8971 | pseudometric_ablation |
| A4 | 0.7195 | -0.1822 | [-0.4166, 0.0000] | 0.8290 | -0.1510 | 0.2748 | 0.7104 | experimental_dissimilarity |
| A5 | 0.9017 | 0.0000 | [0.0000, 0.0000] | 0.9800 | 0.0000 | 0.3195 | 0.8978 | metric_profile |
| A6 | 0.9137 | 0.0120 | [0.0000, 0.0275] | 0.9759 | -0.0041 | 0.3184 | 0.9041 | pseudometric_ablation |
| A7_gamma_1 | 0.8195 | -0.0822 | [-0.2288, 0.0218] | 0.9592 | -0.0208 | 0.3139 | 0.8031 | metric_profile |
| A7_gamma_2 | 0.8504 | -0.0513 | [-0.1430, 0.0218] | 0.9745 | -0.0055 | 0.3184 | 0.8314 | metric_profile |
| A7_gamma_3 | 0.8639 | -0.0378 | [-0.0967, 0.0079] | 0.9745 | -0.0055 | 0.3184 | 0.8649 | metric_profile |
| A7_gamma_4 | 0.8793 | -0.0224 | [-0.0512, 0.0000] | 0.9787 | -0.0014 | 0.3195 | 0.8700 | metric_profile |
| A7_gamma_6 | 0.9017 | 0.0000 | [0.0000, 0.0000] | 0.9800 | 0.0000 | 0.3195 | 0.8978 | metric_profile |

## 7. Sensibilidad a la segmentación (E6)

| Fold | ε | Modo | D_gamma medio | Índice relativo medio | Cambio de correspondencia | Cambio de rango |
|---:|---:|---|---:|---:|---:|---:|
| 1 | 1/100 | internal | 7/15 | 95651/33516000 | 1.0000 | 0.0381 |
| 1 | 1/100 | boundary_start | 35404091/125675550 | 11072521/7037830800 | 1.0000 | 0.0286 |
| 1 | 1/100 | boundary_end | 28914709/125675550 | 191175331/133718785200 | 1.0000 | 0.0429 |
| 1 | 1/100 | boundary_both | 46296983/186609150 | 108940187/74457050850 | 1.0000 | 0.0190 |
| 1 | 1/50 | internal | 116/175 | 1133/232750 | 1.0000 | 0.0619 |
| 1 | 1/50 | boundary_start | 1100291/2488122 | 1951277/696674160 | 1.0000 | 0.0619 |
| 1 | 1/50 | boundary_end | 28914709/62203050 | 191175331/66184045200 | 1.0000 | 0.0619 |
| 1 | 1/50 | boundary_both | 169252031/344509200 | 21027966773/7147876881600 | 1.0000 | 0.0429 |
| 1 | 1/20 | internal | 67/70 | 40699/4468800 | 1.0000 | 0.1286 |
| 1 | 1/20 | boundary_start | 399071/964782 | 147403/30015440 | 1.0000 | 0.0905 |
| 1 | 1/20 | boundary_end | 77999027/72358650 | 1637499529/230968810800 | 1.0000 | 0.1762 |
| 1 | 1/20 | boundary_both | 234664691/217075950 | 823689527/115484405400 | 1.0000 | 0.1524 |
| 2 | 1/100 | internal | 2217/2200 | 843275267111/733006387872000 | 1.0000 | 0.0000 |
| 2 | 1/100 | boundary_start | 2261500781/2681618940 | 13286783318191/18643472988940800 | 1.0000 | 0.0000 |
| 2 | 1/100 | boundary_end | 2253419629/2681618940 | 5226102355807/6967762632230400 | 1.0000 | 0.0000 |
| 2 | 1/100 | boundary_both | 3864427951/5087852770 | 571919338332893/872518720724851200 | 1.0000 | 0.0000 |
| 2 | 1/50 | internal | 288/275 | 611390041367/366503193936000 | 1.0000 | 0.0000 |
| 2 | 1/50 | boundary_start | 12575933/17237220 | 19472151103/18566554406400 | 1.0000 | 0.0000 |
| 2 | 1/50 | boundary_end | 1192727/1567020 | 782775658669/686962513036800 | 1.0000 | 0.0000 |
| 2 | 1/50 | boundary_both | 2878363/4221360 | 332902677427/336471434956800 | 1.0000 | 0.0000 |
| 2 | 1/20 | internal | 63/110 | 312281/221062050 | 1.0000 | 0.0000 |
| 2 | 1/20 | boundary_start | 7368/13585 | 13379/9884160 | 1.0000 | 0.0000 |
| 2 | 1/20 | boundary_end | 1953/4180 | 58981/48591360 | 1.0000 | 0.0000 |
| 2 | 1/20 | boundary_both | 265781/489060 | 3134773/2316188160 | 1.0000 | 0.0000 |
| 3 | 1/100 | internal | 457/240 | 57951671273/42018835622400 | 1.0000 | 0.0000 |
| 3 | 1/100 | boundary_start | 14115970039181147/11692577626329600 | 30176675601271076270611/43304434856665462813132800 | 1.0000 | 0.0000 |
| 3 | 1/100 | boundary_end | 24079485917/16280732160 | 148927877312600893/180891141655696496640 | 1.0000 | 0.0152 |
| 3 | 1/100 | boundary_both | 6682690808557334453209/5005141757907645150720 | 16050656877564079329615798869/21907315499201199682122099271680 | 1.0000 | 0.0152 |
| 3 | 1/50 | internal | 379/150 | 856836276047/399178938412800 | 1.0000 | 0.0152 |
| 3 | 1/50 | boundary_start | 206722123/159042240 | 50920359298261/47259855840637440 | 1.0000 | 0.0152 |
| 3 | 1/50 | boundary_end | 62560430699/31808448000 | 359822959016010307/248699942231457024000 | 1.0000 | 0.0000 |
| 3 | 1/50 | boundary_both | 287327885947757/158787123264000 | 5746093054918100711399/4401699673482356813568000 | 1.0000 | 0.0000 |
| 3 | 1/20 | internal | 3/8 | 822740743/2437733975040 | 1.0000 | 0.0000 |
| 3 | 1/20 | boundary_start | 2547877/3076480 | 75970243673/102791115947520 | 1.0000 | 0.0000 |
| 3 | 1/20 | boundary_end | 93145757/56530320 | 24689355931/18547824113280 | 1.0000 | 0.0303 |
| 3 | 1/20 | boundary_both | 8388032159/4070183040 | 461887204658171/271985292797137920 | 1.0000 | 0.0303 |
| 4 | 1/100 | internal | 21/100 | 881/672000 | 0.6154 | 0.0492 |
| 4 | 1/100 | boundary_start | 118243117/971890920 | 77437579/116626910400 | 0.6154 | 0.0308 |
| 4 | 1/100 | boundary_end | 112835843/971890920 | 79231151/116626910400 | 0.6154 | 0.0462 |
| 4 | 1/100 | boundary_both | 47884199/481036920 | 5771959/12827651200 | 0.6154 | 0.0431 |
| 4 | 1/50 | internal | 19/65 | 5519/2184000 | 0.6154 | 0.1138 |
| 4 | 1/50 | boundary_start | 118243117/481036920 | 77437579/57724430400 | 0.6154 | 0.1231 |
| 4 | 1/50 | boundary_end | 112835843/481036920 | 79231151/57724430400 | 0.6154 | 0.0769 |
| 4 | 1/50 | boundary_both | 47884199/235609920 | 5771959/6282931200 | 0.6154 | 0.0615 |
| 4 | 1/20 | internal | 11/26 | 1361/232960 | 0.6154 | 0.1692 |
| 4 | 1/20 | boundary_start | 2389627/6016920 | 5699/1735650 | 0.6154 | 0.1754 |
| 4 | 1/20 | boundary_end | 399878753/746098080 | 17490454729/5013779097600 | 0.6154 | 0.2246 |
| 4 | 1/20 | boundary_both | 50858221819/99044520120 | 9621621521/3961780804800 | 0.6154 | 0.1631 |
| 5 | 1/100 | internal | 1289/2000 | 89275726517/71158636048500 | 1.0000 | 0.0000 |
| 5 | 1/100 | boundary_start | 42473/118800 | 361902129481/493728025190400 | 1.0000 | 0.0000 |
| 5 | 1/100 | boundary_end | 963719/1425600 | 18333457734071611/25969600396989849600 | 1.0000 | 0.0462 |
| 5 | 1/100 | boundary_both | 9565987/13970880 | 16782669703736647/23136553080954593280 | 1.0000 | 0.0462 |
| 5 | 1/50 | internal | 127/200 | 2740873380299/1301186487744000 | 1.0000 | 0.0462 |
| 5 | 1/50 | boundary_start | 102929/235200 | 29905449953/22215494246400 | 1.0000 | 0.0692 |
| 5 | 1/50 | boundary_end | 133451/235200 | 4985553113579/4376452366540800 | 1.0000 | 0.0462 |
| 5 | 1/50 | boundary_both | 1396501/2483712 | 38861774767999/33010954993336320 | 1.0000 | 0.0462 |
| 5 | 1/20 | internal | 123/200 | 112909495337/36988042291200 | 1.0000 | 0.0692 |
| 5 | 1/20 | boundary_start | 7329/15200 | 26931/9900800 | 1.0000 | 0.0692 |
| 5 | 1/20 | boundary_end | 5303/15200 | 59979377/29910316800 | 1.0000 | 0.0692 |
| 5 | 1/20 | boundary_both | 10499/26400 | 115889621/51949497600 | 1.0000 | 0.0692 |

## 8. Distribuciones intra/inter-familia (por fold)

### Fold 1 — bachBWV889Fg

Parámetros: `{'omega_pc': '1/2', 'omega_lin': '1/2', 'omega_on': '2', 'omega_off': '2', 'gamma': '6'}`

| Conjunto | n | media | mediana | Q1 | Q3 | mín | máx |
|---|---:|---:|---:|---:|---:|---:|---:|
| within | 64 | 1175054029/46425600 | 17533/1040 | 204427/14880 | 7889/208 | 4 | 701/8 |
| between | 146 | 644073913/7060560 | 30793543/241800 | 327629/14880 | 8654961/64480 | 3005/312 | 26257/180 |

`within_between_separation_probability`: 0.8624

### Fold 2 — beethovenOp2No1Mvt3

Parámetros: `{'omega_pc': '1/2', 'omega_lin': '1/2', 'omega_on': '1', 'omega_off': '1', 'gamma': '6'}`

| Conjunto | n | media | mediana | Q1 | Q3 | mín | máx |
|---|---:|---:|---:|---:|---:|---:|---:|
| within | 30 | 4339/520 | 0 | 0 | 287/12 | 0 | 287/12 |
| between | 61 | 774784493591/2303220920 | 165951/820 | 1229/24 | 2547443/3772 | 359/8 | 146875/184 |

`within_between_separation_probability`: 1.0000

### Fold 3 — chopinOp24No4

Parámetros: `{'omega_pc': '1/2', 'omega_lin': '1/2', 'omega_on': '1', 'omega_off': '1', 'gamma': '6'}`

| Conjunto | n | media | mediana | Q1 | Q3 | mín | máx |
|---|---:|---:|---:|---:|---:|---:|---:|
| within | 30 | 399605498230639/4517903174400 | 3523411/34040 | 5330749891/220170720 | 420933/3404 | 0 | 1503347/6624 |
| between | 4 | 33587981027/18458880 | 25190925251/13844160 | 4380934237/2407680 | 508919983/279680 | 11528051/6336 | 95429171/52440 |

`within_between_separation_probability`: 1.0000

### Fold 4 — gibbonsSilverSwan1612

Parámetros: `{'omega_pc': '1/2', 'omega_lin': '1/2', 'omega_on': '1', 'omega_off': '1', 'gamma': '6'}`

| Conjunto | n | media | mediana | Q1 | Q3 | mín | máx |
|---|---:|---:|---:|---:|---:|---:|---:|
| within | 89 | 8518969/1158780 | 1415/168 | 289/56 | 19/2 | 0 | 317/24 |
| between | 236 | 24917285639/178217760 | 681/56 | 869/84 | 2393/168 | 141/56 | 37667/58 |

`within_between_separation_probability`: 0.8351

### Fold 5 — mozartK282Mvt2

Parámetros: `{'omega_pc': '1/2', 'omega_lin': '1/2', 'omega_on': '1', 'omega_off': '1', 'gamma': '6'}`

| Conjunto | n | media | mediana | Q1 | Q3 | mín | máx |
|---|---:|---:|---:|---:|---:|---:|---:|
| within | 111 | 3329/370 | 0 | 0 | 769/32 | 0 | 769/32 |
| between | 133 | 33226603/150480 | 17779/480 | 363/20 | 42929/176 | 1957/120 | 912049/864 |

`within_between_separation_probability`: 0.9122

`macro_within_between_separation_probability`: 0.9220

## 9. Análisis de sensibilidad: consultas no triviales

| Consultas totales | Retenidas (no triviales) | Retiradas (sin negativos) | mAP | MRR | R@1 | R@10 |
|---:|---:|---:|---:|---:|---:|---:|
| 121 | 109 | 12 | 0.8909 | 0.9778 | 0.3075 | 0.8865 |

Scopes afectados: `['beethovenOp2No1Mvt3/tomCollins', 'chopinOp24No4/barlowAndMorgensternRevised', 'mozartK282Mvt2/tomCollins']`

## 10. Warnings de scopes con una sola familia

| Scope | Familias | Ocurrencias | Consultas elegibles | Consultas sin negativos |
|---|---:|---:|---:|---:|
| `beethovenOp2No1Mvt3/tomCollins` | 1 | 2 | 2 | 2 |
| `chopinOp24No4/barlowAndMorgensternRevised` | 1 | 8 | 8 | 8 |
| `mozartK282Mvt2/tomCollins` | 1 | 2 | 2 | 2 |

## 11. Consultas excluidas (protocolo original)

`[]`

## 12. Advertencias de reproducibilidad y otras

- (ninguna)

## 13. Interpretación

Distinción: `observed` (observado), `not observed` (no observado), `inconclusive` (no concluyente).
Las conclusiones quedan limitadas al corpus y protocolo ejecutados; no se emiten conclusiones musicológicas fuertes.
