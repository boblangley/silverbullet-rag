---
displayName: AI Proposals
---
#meta

# Pending Proposals

${query[[
  from index.tag "proposal"
  where status = "pending"
  order by created_at desc
  render [[Library/AI-Proposals/Templates/ProposalRow]]
]]}

# Recently Accepted

${query[[
  from index.tag "proposal"
  where status = "accepted"
  order by created_at desc
  limit 10
  render [[Library/AI-Proposals/Templates/ProposalRow]]
]]}

# Recently Rejected

${query[[
  from index.tag "proposal"
  where status = "rejected"
  order by created_at desc
  limit 10
  render [[Library/AI-Proposals/Templates/ProposalRow]]
]]}
