# References

Companion document for the Medium article:
**"Feature Freshness: The Forgotten Problem of MLOps"**

---

## Feature Stores

| Title | Source | URL |
|---|---|---|
| Feast — Open Source Feature Store | Feast | https://docs.feast.dev |
| Feast: Bridging ML Models and Data | Gojek Engineering | https://www.gojek.io/blog/feast-bridging-ml-models-and-data |
| Feature Store for Machine Learning | Hopsworks | https://www.hopsworks.ai/post/feature-store-the-missing-data-layer-for-machine-learning-pipelines |
| Tecton: The Enterprise Feature Store | Tecton | https://docs.tecton.ai |
| Building a Scalable ML Feature Store | Airbnb Engineering | https://medium.com/airbnb-engineering/building-airbnbs-ml-platform-part-1-9b9f8ba7b8e |
| The Feature Store: A Key MLOps Component | Databricks | https://www.databricks.com/blog/2020/06/19/what-is-feature-store.html |

---

## Streaming and Windowed Aggregation

| Title | Source | URL |
|---|---|---|
| Apache Flink — Stateful Computations over Data Streams | Apache | https://flink.apache.org |
| Apache Flink — Windowing | Apache | https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/operators/windows/ |
| Apache Kafka — Introduction | Apache | https://kafka.apache.org/intro |
| Structured Streaming Programming Guide | Apache Spark | https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html |
| Watermarks in Apache Beam | Apache | https://beam.apache.org/documentation/programming-guide/#watermarks-and-late-data |
| Streamingwithflink.com — Time and Windows | Fabian Hueske & Vasiliki Kalavri | https://www.oreilly.com/library/view/stream-processing-with/9781491974285/ |

---

## MLOps and Model Monitoring

| Title | Source | URL |
|---|---|---|
| Continuous Training for Machine Learning | Google Cloud Architecture | https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning |
| ML Monitoring: What It Is, Why It Matters | Evidently AI | https://www.evidentlyai.com/ml-in-production/ml-monitoring |
| Monitoring ML Models in Production | Chip Huyen | https://huyenchip.com/2022/02/07/data-distribution-shifts-and-monitoring.html |
| Rules of Machine Learning (Rule #29: Identify features important to serve | Google | https://developers.google.com/machine-learning/guides/rules-of-ml |
| Real-Time Machine Learning: Challenges and Solutions | Shreya Shankar et al. (2022) | https://arxiv.org/abs/2111.03014 |
| Hidden Technical Debt in Machine Learning Systems | Sculley et al. (NIPS 2015) | https://papers.nips.cc/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html |

---

## Data Pipeline Engineering

| Title | Source | URL |
|---|---|---|
| Lessons Learned from Running Apache Kafka at Scale | Confluent | https://www.confluent.io/blog/apache-kafka-at-scale/ |
| Redis as a Feature Store | Redis | https://redis.io/solutions/ai-ml/ |
| Handling Late Data in Stream Processing | Ververica | https://www.ververica.com/blog/a-practical-guide-to-broadcast-state-in-apache-flink |
| Point-in-Time Correct Feature Retrieval | Feast Docs | https://docs.feast.dev/getting-started/concepts/point-in-time-joins |
| Exactly-once Semantics in Apache Kafka | Confluent | https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/ |

---

## Production ML Case Studies

| Title | Source | URL |
|---|---|---|
| Michelangelo: Uber's Machine Learning Platform | Uber Engineering | https://www.uber.com/blog/michelangelo-machine-learning-platform/ |
| Metaflow: A Framework for Real-Life Data Science | Netflix Tech Blog | https://netflixtechblog.com/open-sourcing-metaflow-a-human-centric-framework-for-data-science-fa72e04a5d9 |
| Using Apache Kafka for Real-Time Fraud Detection | Confluent | https://www.confluent.io/blog/apache-kafka-for-fraud-detection-real-time/ |
| Zipline: Airbnb's Declarative Feature Engineering Framework | Airbnb Engineering | https://medium.com/airbnb-engineering/zipline-airbnbs-declarative-feature-engineering-framework-d85ca3f5d4e6 |
| Scaling Machine Learning at Uber | Uber Engineering | https://www.uber.com/blog/scaling-machine-learning-at-uber/ |
| Near Real-Time Features for Fraud Detection | Stripe Engineering | https://stripe.com/blog/online-migrations |

---

## Academic Papers

| Title | Authors | Venue | URL |
|---|---|---|---|
| The ML Test Score: A Rubric for ML Production Readiness | Breck et al. (2017) | IEEE Big Data | https://storage.googleapis.com/pub-tools-public-publication-data/pdf/aad9f93b86b7addfea4c419b9100c6cdd26cacea.pdf |
| Data Management Challenges in Production Machine Learning | Polyzotis et al. (2017) | SIGMOD | https://dl.acm.org/doi/10.1145/3035918.3054782 |
| Feature Engineering for Machine Learning | Alice Zheng & Amanda Casari | O'Reilly | https://www.oreilly.com/library/view/feature-engineering-for/9781491953235/ |
| Towards ML Engineering: A Brief History of TensorFlow Extended | Baylor et al. (2022) | arXiv | https://arxiv.org/abs/2010.02013 |

---

## Python Standard Library References

All code in this repository uses only the Python standard library (no NumPy, no pandas).

| Module | Relevance |
|---|---|
| `collections.deque` | O(1) amortized append/popleft for sliding windows |
| `datetime` | Timezone-aware timestamp arithmetic |
| `dataclasses` | Structured data with minimal boilerplate |
| `warnings` | Issuing FreshnessWarning without stopping execution |
| `typing` | Type annotations for Python 3.9 compatibility |

Documentation: https://docs.python.org/3/library/

---

## Tools Used in Production Architectures (Section 8)

| Tool | Role | URL |
|---|---|---|
| Apache Kafka | Durable event ingestion, replay | https://kafka.apache.org |
| Apache Flink | Stateful stream processing, windowing | https://flink.apache.org |
| Redis | Online feature store (<10ms P99) | https://redis.io |
| Feast | Open-source feature platform | https://feast.dev |
| Tecton | Managed feature store | https://tecton.ai |
| Hopsworks | Open-source feature platform | https://hopsworks.ai |
| Apache Spark | Batch feature computation | https://spark.apache.org |
| Prometheus | Feature freshness metrics | https://prometheus.io |
| Grafana | Freshness dashboards | https://grafana.com |
