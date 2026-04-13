// SPDX-License-Identifier: MIT
#include "tuner_core/hardware_presets.hpp"

#include <algorithm>
#include <string>

namespace tuner_core::hardware_presets {

const std::vector<IgnitionPreset>& ignition_presets() {
    static const std::vector<IgnitionPreset> presets = {
        {"single_coil_distributor", "Single Coil / Distributor",
         "Conservative starter dwell for a basic inductive single-coil distributor setup.",
         3.5, 4.5,
         "Conservative inferred starter preset. Review against the ignition module or coil datasheet.", ""},
        {"gm_ls_10457730", "GM LS Coil PN 10457730",
         "Holley-tested maximum dwell for this GM LS coil family.",
         5.0, 5.0,
         "Holley LS harness instructions list 5.0 ms as the maximum dwell for GM coil PN 10457730.",
         "https://documents.holley.com/199r10515rev3.pdf"},
        {"gm_ls_19005218", "GM LS Coil PN 19005218",
         "Holley-tested maximum dwell for this GM LS coil family.",
         4.5, 4.5,
         "Holley LS harness instructions list 4.5 ms as the maximum dwell for GM coil PN 19005218.",
         "https://documents.holley.com/199r10515rev3.pdf"},
        {"gm_ls_12573190_family", "GM LS Coil PN 12573190 / 12611424 / 12570616",
         "Holley-tested maximum dwell for later GM LS coil part numbers in this family.",
         3.5, 3.5,
         "Holley LS harness instructions list 3.5 ms as the maximum dwell for these GM coil part numbers.",
         "https://documents.holley.com/199r10515rev3.pdf"},
        {"gm_d581_12558693", "GM D581 / PN 12558693 Square Coil",
         "Classic GM truck square coil starter preset for remote-mount LS and swap applications.",
         3.5, 3.5,
         "The MSExtra hardware manual recommends 3.5 ms dwell for GM truck coils.",
         "https://www.msextra.com/doc/general/sparkout-v30.html"},
        {"toyota_cop_90919_02248", "Toyota COP 90919-02248 (1ZZ / 2ZZ / 1NZ family)",
         "Common Toyota coil-on-plug used in 1ZZ, 2ZZ, and 1NZ engines.",
         3.0, 4.0,
         "MSExtra and community resources list 3.0 ms running dwell for the Toyota 90919-02248 COP family.",
         "https://www.msextra.com/doc/general/sparkout-v30.html"},
        {"ford_cop_bim_coil", "Ford COPe / BIM-style COP (DG508 / FD487)",
         "Common Ford coil-on-plug used in Modular V8 and some inline applications.",
         3.0, 4.0,
         "MSExtra community resources list 3.0 ms running dwell for Ford Modular COP.",
         "https://www.msextra.com/doc/general/sparkout-v30.html"},
        {"generic_wasted_spark", "Generic Wasted-Spark Coil Pack",
         "Conservative starter preset for a typical wasted-spark coil pack with an internal ignitor.",
         3.5, 4.5,
         "Conservative inferred starter preset for a typical wasted-spark coil pack.", ""},
    };
    return presets;
}

const IgnitionPreset* ignition_preset_by_key(const std::string& key) {
    for (const auto& p : ignition_presets()) {
        if (p.key == key) return &p;
    }
    return nullptr;
}

std::string source_confidence_label(const std::string& source_note,
                                     const std::string& source_url) {
    std::string note_lower = source_note;
    for (auto& c : note_lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));

    if (note_lower.find("inferred") != std::string::npos || source_url.empty())
        return "Starter";

    if (source_url.find("holley.com") != std::string::npos ||
        source_url.find("injectordynamics.com") != std::string::npos ||
        source_url.find("chevrolet.com") != std::string::npos)
        return "Official";

    if (source_url.find("msextra.com") != std::string::npos ||
        source_url.find("ms4x.net") != std::string::npos ||
        source_url.find("injector-rehab.com") != std::string::npos)
        return "Trusted Secondary";

    return "Sourced";
}

}  // namespace tuner_core::hardware_presets
