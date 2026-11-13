| doc | golden sensitivity | golden unsafe | sensitivity correct: base -> new | unsafe correct: base -> new |
|---|---|---|---|---|
| TC1 | Public | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| TC2 | Highly Sensitive | no | 0/3 -> 0/3 | 3/3 -> 3/3 |
| TC3 | Confidential | no | 0/3 -> 0/3 | 3/3 -> 3/3 |
| TC4 | Confidential | no | 0/3 -> 0/3 | 3/3 -> 3/3 |
| SYN01 | Public | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN02 | Public | no | 1/3 -> 0/3 | 3/3 -> 3/3 |
| SYN03 | Public | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN04 | Public | yes | 3/3 -> 3/3 | 0/3 -> 3/3 **fixed** |
| SYN05 | Public | yes | 3/3 -> 3/3 | 0/3 -> 3/3 **fixed** |
| SYN06 | Public | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN07 | Public | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN08 | Confidential | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN09 | Confidential | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN10 | Confidential | no | 3/3 -> 0/3 **regressed** | 3/3 -> 3/3 |
| SYN11 | Confidential | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN12 | Confidential | yes | 0/3 -> 3/3 **fixed** | 3/3 -> 3/3 |
| SYN13 | Confidential | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN14 | Confidential | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN15 | Highly Sensitive | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN16 | Highly Sensitive | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN17 | Highly Sensitive | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN18 | Highly Sensitive | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN19 | Highly Sensitive | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN20 | Highly Sensitive | no | 3/3 -> 3/3 | 3/3 -> 3/3 |
| SYN21 | Highly Sensitive | yes | 2/3 -> 3/3 **fixed** | 1/3 -> 3/3 **fixed** |
| SYN22 | Public | yes | 0/3 -> 3/3 **fixed** | 3/3 -> 3/3 |
| SYN23 | Confidential | yes | 0/3 -> 0/3 | 2/3 -> 3/3 **fixed** |
| SYN24 | Highly Sensitive | yes | 3/3 -> 3/3 | 0/3 -> 3/3 **fixed** |
