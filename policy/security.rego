package main

deny[msg] {
  input.kind == "ProjectNetworkPolicy"
  some i, j, k
  input.spec.ingress[i].from[j].ipBlock.cidr == "0.0.0.0/0"
  msg = sprintf("ProjectNetworkPolicy '%s' allows ingress from 0.0.0.0/0, which is too permissive.", [input.metadata.name])
}

deny[msg] {
  input.kind == "ProjectNetworkPolicy"
  some i, j, k
  input.spec.egress[i].to[j].ipBlock.cidr == "0.0.0.0/0"
  msg = sprintf("ProjectNetworkPolicy '%s' allows egress to 0.0.0.0/0, which is too permissive.", [input.metadata.name])
}
