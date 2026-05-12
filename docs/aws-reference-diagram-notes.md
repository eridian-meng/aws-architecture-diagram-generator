# AWS Reference Diagram Notes

These notes summarize the layout and styling patterns observed in the AWS reference materials that should drive the renderer.

## Primary References

- AWS Architecture Icons: https://aws.amazon.com/architecture/icons/
- Traffic Encryption Options in AWS Direct Connect: https://d1.awsstatic.com/architecture-diagrams/ArchitectureDiagrams/traffic-encryption-options-direct-connect-ra.pdf?did=wp_card&trk=wp_card
- Hybrid connectivity between AWS GovCloud and commercial Regions: https://d1.awsstatic.com/architecture-diagrams/ArchitectureDiagrams/hybrid-connectivity-between-aws-govcloud-and-commercial-regions.pdf?did=wp_card&trk=wp_card
- Active/Active and Active/Passive Configurations in AWS Direct Connect: https://docs.aws.amazon.com/architecture-diagrams/latest/active-active-and-active-passive-configurations-in-aws-direct-connect/active-active-and-active-passive-configurations-in-aws-direct-connect.html?did=wp_card&trk=wp_card

## Observed Conventions

### 1. Icons are official and current

AWS explicitly provides an official architecture icon set for diagramming. Production output from this project should use those icons rather than generic rounded boxes or third-party sets.

### 2. Boundaries are nested and visually quiet

The diagrams consistently use nested containers for:

- AWS cloud
- region
- VPC
- availability zone
- subnet

The boundaries frame the layout without overpowering the service icons.

### 3. Traffic flow is separate from object placement

AWS reference diagrams keep traffic lines in deliberate lanes. Flows usually travel around or between objects instead of through them. This is the right model for the renderer:

- reserve whitespace for connectors
- prefer orthogonal connectors
- avoid overlapping icons and labels
- use arrowheads only where direction matters

### 4. Complex flows get a side narrative

When traffic has multiple steps, AWS often uses numbered markers in the main diagram and explains them in a dedicated right-side column. This means the renderer should support:

- optional numbered step badges
- optional right-side flow explanation panel
- optional legends for connector semantics

### 5. Tables and legends stay outside the core workload area

When route tables or attachment mappings are useful, AWS places them beside the main topology rather than embedding them inside the resource area. The result is cleaner and easier to scan.

### 6. Color conveys category

In the references, color is purposeful. Different colors help distinguish:

- service categories
- network types
- region or environment boundaries
- different traffic types

The renderer should therefore assign color semantically and consistently instead of styling each node independently.

### 7. Labels are concise and readable

Labels are short, aligned, and usually placed below or beside icons. Long explanations go into side text, not into the topology area itself.

## Implications For This Project

The renderer should support at least two output modes:

1. Topology-only mode
2. Topology plus flow-notes mode

The first mode is best for account overviews. The second is best when the user wants to understand how traffic moves through the architecture.
