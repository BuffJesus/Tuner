// SPDX-License-Identifier: MIT
#include "tuner_core/curve_page_builder.hpp"

#include <algorithm>
#include <map>
#include <string>

namespace tuner_core::curve_page_builder {

namespace cpc = tuner_core::curve_page_classifier;

std::vector<CurvePageGroup> build_curve_pages(
    const std::vector<CurveDefinition>& curves,
    ParamFinder find_param,
    void* find_param_user)
{
    if (curves.empty()) return {};

    // Group key: (order, group_id, group_title) → pages
    struct GroupKey {
        int order;
        std::string group_id;
        std::string group_title;
        bool operator<(const GroupKey& o) const {
            if (order != o.order) return order < o.order;
            return group_id < o.group_id;
        }
    };
    std::map<GroupKey, std::vector<CurvePage>> grouped;

    for (const auto& curve : curves) {
        CurvePage page;
        page.page_id = "curve:" + curve.name;
        page.title = curve.title;
        page.help_topic = curve.topic_help;
        page.x_axis_label = curve.x_label;
        page.y_axis_label = curve.y_label;
        page.curve_name = curve.name;
        page.curve_x_bins_param = curve.x_bins_param;
        page.curve_x_channel = curve.x_channel;
        page.curve_gauge = curve.gauge;

        // X-axis parameter
        auto x_info = find_param(curve.x_bins_param, find_param_user);
        if (x_info) {
            CurveParameter cp;
            cp.name = x_info->name;
            cp.label = curve.x_label.empty() ? x_info->label : curve.x_label;
            cp.units = x_info->units;
            cp.role = "x_axis";
            page.parameters.push_back(std::move(cp));
        }

        // Y-axis parameters
        for (const auto& yb : curve.y_bins_list) {
            page.curve_y_bins_params.push_back(yb.param);
            page.curve_line_labels.push_back(yb.label);

            auto y_info = find_param(yb.param, find_param_user);
            if (y_info) {
                CurveParameter cp;
                cp.name = y_info->name;
                std::string label = yb.label;
                if (label.empty()) label = curve.y_label;
                if (label.empty()) label = y_info->label;
                if (label.empty()) label = y_info->name;
                cp.label = label;
                cp.units = y_info->units;
                cp.role = "y_axis";
                page.parameters.push_back(std::move(cp));
            }
        }

        page.summary = cpc::summary(
            static_cast<int>(curve.y_bins_list.size()),
            curve.x_channel);

        auto ga = cpc::classify(curve.name, curve.title);
        page.group_id = "curve-" + ga.group_id;
        page.group_title = ga.group_title;
        page.group_order = ga.order;

        GroupKey key{ga.order, "curve-" + ga.group_id, ga.group_title};
        grouped[key].push_back(std::move(page));
    }

    // Sort pages within each group alphabetically by title (lowercased).
    std::vector<CurvePageGroup> result;
    for (auto& [key, pages] : grouped) {
        std::sort(pages.begin(), pages.end(), [](const CurvePage& a, const CurvePage& b) {
            // Case-insensitive sort.
            std::string al = a.title, bl = b.title;
            for (auto& c : al) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            for (auto& c : bl) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            return al < bl;
        });
        CurvePageGroup grp;
        grp.group_id = key.group_id;
        grp.title = key.group_title;
        grp.pages = std::move(pages);
        result.push_back(std::move(grp));
    }
    return result;
}

}  // namespace tuner_core::curve_page_builder
